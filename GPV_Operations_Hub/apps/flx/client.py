"""Read-only HTTP client for the FactoryLogix OData service.

Guarantees (tested in apps/flx/tests):
* Only GET is ever sent. There is no code path that issues POST/PUT/PATCH/DELETE/MERGE.
* The base URL comes from configuration (settings.GPV_FLX["BASE_URL"]); requests can only target
  paths below it, and continuation links (nextLink/__next) must stay on the same scheme, host, port
  and base path.
* Credentials are read from environment variables at call time; they are never stored, logged,
  cached, returned to the browser or written to diagnostic reports. Authorization headers are never logged.
* Transient errors (timeout, 429, 502/503/504) are retried a limited number of times with growing
  pauses; 401/403/404/400 are never retried. After a 401 the connector stops calling the server
  until an administrator retries explicitly or the authentication configuration changes.
* A process-wide circuit breaker pauses calls after repeated transient failures.
* A semaphore limits concurrent calls; successful GET responses are cached for a few seconds.
"""
import base64
import hashlib
import json
import logging
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import status as st

log = logging.getLogger("gpv.flx")
_lock = threading.Lock()
_breaker = {"failures": 0, "open_until": 0.0}
_sem = None


class FlxError(Exception):
    def __init__(self, state, message, http_status=None, detail=""):
        super().__init__(message)
        self.state, self.http_status, self.detail = state, http_status, detail


@dataclass
class FlxResponse:
    status: int
    headers: dict
    body: bytes
    ms: int
    path: str
    cached: bool = False
    attempts: int = 1
    extra: dict = field(default_factory=dict)

    def json(self):
        try:
            return json.loads(self.body.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            raise FlxError(st.BAD_RESPONSE, "La respuesta no es JSON válido (¿página de inicio de sesión, proxy o formato XML?).", self.status)


def cfg():
    return settings.GPV_FLX


def base_url():
    url = (cfg()["BASE_URL"] or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise FlxError(st.CONFIG_ERROR, "GPV_FLX_BASE_URL debe comenzar con http:// o https://.")
    return url.rstrip("/") + "/"


def auth_mode():
    return cfg()["AUTH"] if cfg()["AUTH"] in ("auto", "none", "basic", "negotiate", "ntlm") else "auto"


def auth_fingerprint():
    """Identifies the auth configuration WITHOUT revealing it (used to lift the 401 block when it changes)."""
    user = os.environ.get(cfg()["USER_ENV"], "")
    secret = os.environ.get(cfg()["PASSWORD_ENV"], "")
    return hashlib.sha256(f"{auth_mode()}|{user}|{hashlib.sha256(secret.encode()).hexdigest()}".encode()).hexdigest()[:16]


def resolve(path_or_url):
    """Build a URL below the configured base. Absolute URLs (continuation links) must stay under it."""
    base = base_url()
    if path_or_url.lower().startswith(("http://", "https://")):
        b, u = urllib.parse.urlsplit(base), urllib.parse.urlsplit(path_or_url)
        if (u.scheme.lower(), u.netloc.lower()) != (b.scheme.lower(), b.netloc.lower()) or not u.path.startswith(b.path.rstrip("/")):
            raise FlxError(st.CONFIG_ERROR, "Se rechazó un enlace de continuación que apunta fuera del servicio configurado.")
        return path_or_url
    if ".." in path_or_url or path_or_url.startswith("/"):
        raise FlxError(st.CONFIG_ERROR, "Ruta no permitida.")
    return base + path_or_url


def _safe_path(url):
    """Path + option NAMES only (filter values may contain serials or work orders): for logs/audit."""
    u = urllib.parse.urlsplit(url)
    opts = sorted({k for k, _v in urllib.parse.parse_qsl(u.query, keep_blank_values=True)})
    return u.path + (("?" + "&".join(opts)) if opts else "")


def _semaphore():
    global _sem
    with _lock:
        if _sem is None:
            _sem = threading.BoundedSemaphore(max(1, cfg()["CONCURRENCY"]))
        return _sem


def reset_runtime():
    """Tests / admin: reset breaker and semaphore (does not touch the auth block)."""
    global _sem
    with _lock:
        _breaker.update(failures=0, open_until=0.0)
        _sem = None


def breaker_state():
    with _lock:
        remaining = max(0, int(_breaker["open_until"] - time.monotonic()))
        return {"open": remaining > 0, "seconds_left": remaining, "failures": _breaker["failures"]}


def _breaker_check():
    with _lock:
        if _breaker["open_until"] > time.monotonic():
            raise FlxError(st.CIRCUIT_OPEN, f"Consultas en pausa {int(_breaker['open_until'] - time.monotonic())} s por fallas repetidas del servidor.")


def _breaker_result(ok):
    with _lock:
        if ok:
            _breaker.update(failures=0, open_until=0.0)
        else:
            _breaker["failures"] += 1
            if _breaker["failures"] >= cfg()["BREAKER_FAILURES"]:
                _breaker["open_until"] = time.monotonic() + cfg()["BREAKER_COOLDOWN"]


# ---------------------------------------------------------------- transports
def _opener():
    handlers = [] if cfg()["USE_SYSTEM_PROXY"] else [urllib.request.ProxyHandler({})]  # internal server: no proxy by default
    return urllib.request.build_opener(*handlers)


def _basic_header():
    user, pwd = os.environ.get(cfg()["USER_ENV"]), os.environ.get(cfg()["PASSWORD_ENV"])
    if not user or not pwd:
        raise FlxError(st.CONFIG_ERROR, f"Autenticación básica configurada: defina {cfg()['USER_ENV']} y {cfg()['PASSWORD_ENV']} en este equipo.")
    return "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()


def _send_urllib(url, accept, mode):
    headers = {"Accept": accept, "User-Agent": "GPV-Operations-Hub/2.0 (solo lectura)", "OData-MaxVersion": "4.0", "MaxDataServiceVersion": "3.0"}
    if mode == "basic":
        headers["Authorization"] = _basic_header()
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _opener().open(req, timeout=cfg()["TIMEOUT"]) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(), r.headers.get_all("WWW-Authenticate") or []
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        www = (e.headers.get_all("WWW-Authenticate") if e.headers else None) or []
        body = b""
        try:
            body = e.read()[:2000]
        except Exception:
            pass
        return e.code, hdrs, body, www
    except (socket.timeout, TimeoutError):
        raise FlxError(st.TIMEOUT, f"Sin respuesta en {cfg()['TIMEOUT']} s.")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise FlxError(st.TIMEOUT, f"Sin respuesta en {cfg()['TIMEOUT']} s.")
        raise FlxError(st.UNREACHABLE, f"No se pudo conectar con el servidor ({e.reason.__class__.__name__}). Verifique que el equipo esté en la red de GPV.")
    except OSError as e:
        raise FlxError(st.UNREACHABLE, f"No se pudo conectar ({e.__class__.__name__}).")


def _send_requests(url, accept, mode):
    try:
        import requests
    except ImportError:
        raise FlxError(st.CONFIG_ERROR, "La autenticación Windows/NTLM requiere los paquetes opcionales de requirements-optional.txt (requests y "
                                        "requests-negotiate-sspi o requests-ntlm).")
    if mode == "negotiate":
        try:
            from requests_negotiate_sspi import HttpNegotiateAuth
        except ImportError:
            raise FlxError(st.CONFIG_ERROR, "Falta requests-negotiate-sspi (solo Windows): usa la sesión de Windows del usuario que ejecuta el portal.")
        auth = HttpNegotiateAuth()
    else:
        try:
            from requests_ntlm import HttpNtlmAuth
        except ImportError:
            raise FlxError(st.CONFIG_ERROR, "Falta requests-ntlm para autenticación NTLM con usuario de servicio.")
        user, pwd = os.environ.get(cfg()["USER_ENV"]), os.environ.get(cfg()["PASSWORD_ENV"])
        if not user or not pwd:
            raise FlxError(st.CONFIG_ERROR, f"NTLM configurado: defina {cfg()['USER_ENV']} (DOMINIO\\usuario) y {cfg()['PASSWORD_ENV']}.")
        auth = HttpNtlmAuth(user, pwd)
    s = requests.Session()
    s.trust_env = cfg()["USE_SYSTEM_PROXY"]
    try:
        r = s.get(url, auth=auth, timeout=cfg()["TIMEOUT"], headers={"Accept": accept, "User-Agent": "GPV-Operations-Hub/2.0 (solo lectura)"},
                  allow_redirects=False)
    except requests.Timeout:
        raise FlxError(st.TIMEOUT, f"Sin respuesta en {cfg()['TIMEOUT']} s.")
    except requests.RequestException as e:
        raise FlxError(st.UNREACHABLE, f"No se pudo conectar ({e.__class__.__name__}).")
    www = [v.strip() for v in r.headers.get("WWW-Authenticate", "").split(",") if v.strip()]
    return r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.content, www


def _transport(url, accept, mode):
    if mode in ("negotiate", "ntlm"):
        return _send_requests(url, accept, mode)
    return _send_urllib(url, accept, "basic" if mode == "basic" else "none")


def schemes_from(www_values):
    out = []
    for v in www_values:
        for part in v.split(","):
            word = part.strip().split(" ", 1)[0]
            if word and "=" not in word and word not in out:
                out.append(word)
    return out


# ---------------------------------------------------------------- state bookkeeping
def _record(ok, state_value, detail="", ms=None):
    from .models import FlxState

    now = timezone.now()
    upd = {"last_status": state_value, "last_detail": detail[:500], "last_attempt_at": now, "updated": now, "auth_configured": auth_mode()}
    if ok:
        upd.update(last_success_at=now, last_latency_ms=ms)
    FlxState.objects.update_or_create(pk=1, defaults=upd)


def _auth_blocked():
    from .models import FlxState

    s = FlxState.get()
    if s.auth_blocked_at and s.auth_fingerprint == auth_fingerprint():
        return s
    return None


def clear_auth_block():
    from .models import FlxState

    FlxState.objects.filter(pk=1).update(auth_blocked_at=None)


def _block_auth():
    from .models import FlxState

    FlxState.objects.update_or_create(pk=1, defaults={"auth_blocked_at": timezone.now(), "auth_fingerprint": auth_fingerprint()})


# ---------------------------------------------------------------- public API
def classify_http(code):
    if code == 401:
        return st.AUTH_REQUIRED
    if code == 403:
        return st.FORBIDDEN
    if code == 404:
        return st.NOT_FOUND
    if code == 429:
        return st.RATE_LIMITED
    if code == 400:
        return st.BAD_REQUEST
    if code >= 500:
        return st.SERVER_ERROR
    return st.BAD_RESPONSE


def get(path_or_url, accept="application/json", use_cache=True, force=False, mode=None, record=True, retries=2):
    """GET a resource. Returns FlxResponse for 2xx; raises FlxError otherwise."""
    mode = mode or auth_mode()
    url = resolve(path_or_url)
    if not force and _auth_blocked():
        raise FlxError(st.AUTH_REQUIRED, "El servidor rechazó la autenticación anteriormente; no se reintenta automáticamente. "
                                         "Un administrador puede «Reintentar autenticación» en el Connection Center.", 401)
    key = "flx:" + hashlib.sha256(f"{mode}|{accept}|{url}".encode()).hexdigest()
    if use_cache and cfg()["CACHE_SECONDS"] > 0:
        hit = cache.get(key)
        if hit:
            return FlxResponse(**hit, cached=True)
    _breaker_check()
    sem = _semaphore()
    if not sem.acquire(timeout=cfg()["TIMEOUT"]):
        raise FlxError(st.RATE_LIMITED, "Demasiadas consultas simultáneas a FactoryLogix en este equipo; intente de nuevo.")
    try:
        attempt = 0
        while True:
            attempt += 1
            t0 = time.monotonic()
            try:
                code, headers, body, www = _transport(url, accept, mode)
            except FlxError as e:
                ms = int((time.monotonic() - t0) * 1000)
                log.warning(json.dumps({"event": "flx_get", "path": _safe_path(url), "state": e.state, "ms": ms, "attempt": attempt}))
                if e.state in (st.TIMEOUT,) and attempt <= retries:
                    time.sleep(0.5 * attempt)
                    continue
                if e.state in st.TRANSIENT:
                    _breaker_result(False)
                if record:
                    _record(False, e.state, str(e))
                raise
            ms = int((time.monotonic() - t0) * 1000)
            log.info(json.dumps({"event": "flx_get", "path": _safe_path(url), "status": code, "ms": ms, "attempt": attempt, "bytes": len(body)}))
            if 200 <= code < 300:
                _breaker_result(True)
                resp = FlxResponse(code, headers, body, ms, _safe_path(url), attempts=attempt, extra={"www_authenticate": schemes_from(www)})
                if record:
                    _record(True, st.CONNECTED, "", ms)
                if use_cache and cfg()["CACHE_SECONDS"] > 0 and len(body) < 2_000_000:
                    cache.set(key, {"status": code, "headers": headers, "body": body, "ms": ms, "path": resp.path,
                                    "extra": resp.extra}, cfg()["CACHE_SECONDS"])
                return resp
            state = classify_http(code)
            if code in (429, 502, 503, 504) and attempt <= retries:
                wait = 0.5 * (3 ** (attempt - 1))
                try:
                    wait = min(float(headers.get("retry-after", wait)), 10.0)
                except ValueError:
                    pass
                time.sleep(wait)
                continue
            if state in st.TRANSIENT:
                _breaker_result(False)
            if code == 401:
                _block_auth()
            schemes = schemes_from(www)
            detail = st.EXPLAIN.get(state, "")
            if code == 401 and schemes:
                detail += f" Métodos ofrecidos por el servidor: {', '.join(schemes)}."
            if record:
                _record(False, state, f"HTTP {code}: {detail}")
            err = FlxError(state, f"HTTP {code}: {detail}", code, detail=_server_message(body))
            err.schemes = schemes
            raise err
    finally:
        sem.release()


def _server_message(body):
    """Short server error text for admins (OData error.message), never the full body."""
    try:
        d = json.loads(body.decode("utf-8", "ignore"))
        e = d.get("error") or d.get("odata.error") or {}
        m = e.get("message")
        if isinstance(m, dict):
            m = m.get("value")
        return str(m or "")[:300]
    except Exception:
        return ""


def detect_auth():
    """Anonymous GET of the service root to learn which authentication schemes the server offers.
    Never sends credentials; does not change the configured mode."""
    from .models import FlxState

    try:
        r = get("", use_cache=False, force=True, mode="none", record=False, retries=0)
        result = {"status": r.status, "anonymous_allowed": True, "schemes": r.extra.get("www_authenticate", []), "ms": r.ms}
    except FlxError as e:
        result = {"status": e.http_status, "anonymous_allowed": False, "schemes": getattr(e, "schemes", []), "state": e.state, "message": str(e)}
    FlxState.objects.update_or_create(pk=1, defaults={"auth_schemes_offered": result.get("schemes", []), "auth_detected_at": timezone.now()})
    if not result["anonymous_allowed"] and result.get("state") == st.AUTH_REQUIRED and auth_mode() not in ("none", "auto"):
        clear_auth_block()  # the anonymous probe must not block the configured credentials
    return result
