"""Concurrent HTTP load scenario (stdlib only). Development/IT tool.

  python tools/load_test.py --base http://127.0.0.1:8000 --user admin --password ... --users 10 --requests 20

Each virtual user logs in (CSRF + session) and requests a mix of pages/APIs. Reports
latency percentiles and errors. A small local test does NOT certify capacity for hundreds
of users; repeat on the target server with PostgreSQL and a WSGI server.
"""
import argparse
import http.cookiejar
import re
import statistics
import threading
import time
import urllib.parse
import urllib.request

PATHS = ["/", "/produccion/?period=all", "/analitica/api/dashboard/?period=all", "/api/notificaciones/", "/produccion/registros/?period=all"]
SHIFT_PATHS = ["/turno/", "/turno/api/estado/", "/api/notificaciones/", "/turno/trabajo/", "/turno/api/pantalla/SMT-EJEMPLO/"]


def session(base, user, password):
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    html = op.open(base + "/entrar/").read().decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
    data = urllib.parse.urlencode({"username": user, "password": password, "csrfmiddlewaretoken": token}).encode()
    req = urllib.request.Request(base + "/entrar/", data=data, headers={"Referer": base + "/entrar/"})
    op.open(req).read()
    return op


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--requests", type=int, default=20)
    ap.add_argument("--turno", action="store_true", help="Mezcla del portal del turno (refresco de Mi turno, API de estado y pantalla de área).")
    a = ap.parse_args()
    lat, errors, lock = [], [], threading.Lock()

    def vu(n):
        try:
            op = session(a.base, a.user, a.password)
        except Exception as exc:
            with lock:
                errors.append(f"login: {exc}")
            return
        for i in range(a.requests):
            paths = SHIFT_PATHS if a.turno else PATHS
            path = paths[(n + i) % len(paths)]
            t = time.perf_counter()
            try:
                r = op.open(a.base + path, timeout=60)
                r.read()
                ok = r.status == 200
            except Exception as exc:
                ok = False
                with lock:
                    errors.append(f"{path}: {exc}")
            dt = time.perf_counter() - t
            with lock:
                lat.append(dt) if ok else None

    t0 = time.perf_counter()
    ths = [threading.Thread(target=vu, args=(n,)) for n in range(a.users)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    total = time.perf_counter() - t0
    lat.sort()
    if lat:
        p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))]  # noqa: E731
        print(f"usuarios={a.users} solicitudes_ok={len(lat)} errores={len(errors)} duracion={total:.1f}s rps={len(lat) / total:.1f}")
        print(f"latencia media={statistics.mean(lat) * 1000:.0f}ms p50={p(.5) * 1000:.0f}ms p95={p(.95) * 1000:.0f}ms max={lat[-1] * 1000:.0f}ms")
    for e in errors[:10]:
        print("ERROR", e)


if __name__ == "__main__":
    main()
