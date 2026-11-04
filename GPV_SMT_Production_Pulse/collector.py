"""Centralized background collector: ONE bounded OData query per cycle (default 300 s).

Runs in a single thread of the single application process, independently of browsers:
dashboards read SQLite only, so the number of connected users never changes the load on
FactoryLogix.

Lifecycle of each cycle (``tick``):
1. Validation (startup / after a schema-related error only):
   a. GET ``$metadata`` once and identify the real fields of ProductivityOverTime.
   b. Use the confirmed field mapping (UI or config.json); if none exists and
      ``auto_apply_detected_mapping`` is true, apply the name-based detection, labelled
      *auto-detectado, pendiente de confirmar*.
   c. Run the explicit compatibility probes ($top=1) once per schema+mapping.
   If ``$top`` or the date filter are not verified the collector is BLOCKED: it sends nothing
   and re-validates only every ``probe_recheck_hours``.
2. Collection: one GET ``ProductivityOverTime`` with a validated date window
   ``[start, now)``, ``$top=MAX_RECORDS``, plus ``$select``/``$orderby asc`` only if verified.
   * Normal: ``start = min(cursor, now - lookback)`` so late-arriving or updated records of the
     recent intervals are read again (deduplicated by entity key, changes kept as revisions).
   * If the page is full (more data than ``$top``) and ascending order is verified, the next
     cycle continues from the newest timestamp received (*catching up*) - still one query per
     cycle, never following ``nextLink``.
   * The window never starts earlier than ``initial_backfill_hours`` ago; older gaps are
     reported, not downloaded.
3. Failures (401/403/5xx/timeout/disconnection): last data is kept, a visible warning is shown and
   the next attempt is delayed exponentially (``interval * 2^n`` up to ``max_backoff_seconds``);
   the client circuit breaker adds a second protection. No probe or metadata request is
   repeated while the server does not answer.

Single instance: an OS-level exclusive lock on ``data/collector_<mode>.lock`` prevents a second
process (another console, a scheduled task) from running a parallel collector.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any, Callable

import live_metrics
from analytics import parse_number
from metadata_inspector import best_guess_mapping
from odata_client import LOCAL_REJECTIONS, FilterClause, QuerySpec, Status
from security import odata_datetime_literal
from settings import DIMENSION_ROLES
from timeutil import iso_utc, parse_odata_datetime, utc_now

logger = logging.getLogger("pulse.collector")
COLLECTOR_SESSION = "collector-process-000000"
AUTH_ERRORS = {Status.AUTH_REQUIRED, Status.FORBIDDEN, Status.AUTH_NOT_AVAILABLE}


class SingleInstanceLock:
    """Exclusive, non-blocking OS file lock (msvcrt on Windows, fcntl elsewhere). No admin rights."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} since={iso_utc(utc_now())}\n")
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        self._handle.close()
        self._handle = None


def record_identity(raw: dict[str, Any], keys: list[str], ts: datetime, dims: dict[str, Any]) -> str:
    """Entity key when declared and present; otherwise a hash of timestamp + mapped dimensions."""
    if keys and all(raw.get(k) is not None for k in keys):
        return "k:" + json.dumps([raw[k] for k in keys], ensure_ascii=False, default=str)
    basis = json.dumps([iso_utc(ts), [dims.get(d) for d in DIMENSION_ROLES]], ensure_ascii=False, default=str)
    return "h:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


class Collector:
    """Background collector bound to a ``PulseService``."""

    def __init__(self, service: Any, clock: Callable[[], datetime] = utc_now,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.service = service
        self.config = service.config
        self.settings = service.config.collector
        self.db = service.db
        self.clock = clock
        self.monotonic = monotonic
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._validated = False
        self._metadata_ok = False
        persisted = self.db.get_setting("collector_state") or {}
        self.state: dict[str, Any] = {
            "status": "starting", "message": "Iniciando recolector…", "consecutive_failures": 0,
            "next_run_at": None, "last_attempt_at": None, "last_success_at": persisted.get("last_success_at"),
            "last_error": None, "cursor": persisted.get("cursor"), "catching_up": bool(persisted.get("catching_up")),
            "gaps": persisted.get("gaps", [])[-10:], "coverage_start": persisted.get("coverage_start"), "interval_seconds": self.settings.interval_seconds,
            "warnings": [], "auth": getattr(service.client, "auth_description", "—"),
            "mapping_source": None, "started_at": iso_utc(self.clock()),
        }

    # ------------------------------------------------------------------ thread control
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="pulse-collector", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)
        self.state["status"] = "stopped"

    def _loop(self) -> None:
        logger.info("collector started interval=%ss", self.settings.interval_seconds)
        while not self._stop.is_set():
            try:
                delay = self.tick()
            except Exception:  # noqa: BLE001 - the loop must survive unexpected errors
                logger.exception("collector cycle failed unexpectedly")
                delay = self._backoff("internal_error", "Error interno del recolector; ver logs.")
            self.state["next_run_at"] = iso_utc(self.clock() + timedelta(seconds=delay))
            self._stop.wait(delay)
        logger.info("collector stopped")

    # ------------------------------------------------------------------ helpers
    def _persist(self) -> None:
        self.db.set_setting("collector_state", {k: self.state.get(k) for k in ("cursor", "catching_up", "last_success_at", "gaps",
                                                                      "coverage_start")})

    def _backoff(self, status: str, message: str, http_status: int | None = None, auth: bool = False) -> float:
        self.state["consecutive_failures"] += 1
        n = self.state["consecutive_failures"]
        base = self.settings.interval_seconds
        delay = min(self.settings.max_backoff_seconds, base * (2 ** (n + (1 if auth else 0) - 1)))
        self.state.update(status="backoff", last_error={"status": status, "message": message, "http_status": http_status,
                                                         "at": iso_utc(self.clock())},
                          message=f"{message} Próximo intento en {int(delay // 60)} min.")
        logger.warning("collector backoff status=%s http=%s next=%ss", status, http_status, delay)
        return delay

    # ------------------------------------------------------------------ validation
    def _ensure_validated(self) -> float | None:
        """Return None when ready to collect, else the delay before the next attempt."""
        svc = self.service
        if self._validated and svc.schema and svc.readiness()[0]:
            return None
        if svc.schema is None or not self._metadata_ok:
            result = svc.check_connection(COLLECTOR_SESSION, force=True)
            self._record_admin_run("metadata", result)
            if not result.get("ok"):
                status = result.get("status", "error")
                return self._backoff(status, "No se pudo leer $metadata de FactoryLogix. Se conservan los últimos datos.",
                                     auth=status in {s.value for s in AUTH_ERRORS})
            self._metadata_ok = True
        stored = self.db.get_setting("field_mapping")
        if not stored and not any(self.config.field_mapping.values()) and self.settings.auto_apply_detected_mapping:
            guess = best_guess_mapping(svc.schema)
            if guess.get("timestamp"):
                self.db.set_setting("field_mapping", guess)
                self.db.set_setting("field_mapping_source", "auto")
                logger.info("auto-detected mapping applied (pending MES confirmation): %s", guess)
        self.state["mapping_source"] = svc.mapping_source()
        if not svc.mapping().get("timestamp"):
            self._metadata_ok = False  # re-read metadata at the next (distant) validation
            self.state.update(status="blocked", message="No se identificó un campo de fecha/hora en ProductivityOverTime. "
                                                         "Confirma el mapeo en 'Estado de conexión'.")
            return float(self.settings.probe_recheck_hours * 3600)
        if not svc._valid_probes():
            result = svc.run_capability_probes(COLLECTOR_SESSION, force=True)
            self._record_admin_run("probes", result)
            if not svc._valid_probes():
                # Aborted because the server stopped answering: retry later with backoff (no probe loop).
                return self._backoff(str(result.get("status", "probes_failed")),
                                     "No se completaron las pruebas de compatibilidad: " + str(result.get("message", "")))
        self._validated = True
        ready, reasons = svc.readiness()
        if not ready:
            self.state.update(status="blocked", message="Recolección bloqueada: " + " ".join(reasons))
            logger.warning("collector blocked: %s", reasons)
            self._validated = False  # re-validate after probe_recheck_hours
            self._metadata_ok = False
            return float(self.settings.probe_recheck_hours * 3600)
        if svc.capability("filter_line") != "ok" and svc.mapping().get("line"):
            self.state["warnings"] = ["El filtro por línea no está comprobado en FactoryLogix; el recolector no lo necesita "
                                      "(lee todas las líneas en la ventana de tiempo) y la separación por línea se hace localmente."]
        return None

    def _record_admin_run(self, kind: str, result: dict[str, Any]) -> None:
        run_id = self.db.start_run(kind)
        self.db.finish_run(run_id, status="ok" if result.get("ok") else str(result.get("status", "error")),
                           message=str(result.get("message", ""))[:500])

    # ------------------------------------------------------------------ collection
    def compute_window(self, now: datetime) -> tuple[datetime, datetime, list[dict[str, str]]]:
        """Return (start, end, new_gaps) for this cycle."""
        backfill_floor = now - timedelta(hours=self.settings.initial_backfill_hours)
        cursor = datetime.fromisoformat(self.state["cursor"]) if self.state.get("cursor") else backfill_floor
        if self.state.get("catching_up"):
            start = cursor
        else:
            start = min(cursor, now - timedelta(minutes=self.settings.lookback_minutes))
        gaps: list[dict[str, str]] = []
        if start < backfill_floor:
            gaps.append({"from": iso_utc(start), "to": iso_utc(backfill_floor),
                         "reason": "Fuera de la ventana de recuperación configurada (initial_backfill_hours)."})
            start = backfill_floor
        return start.replace(microsecond=0), now.replace(microsecond=0), gaps

    def normalize(self, raw_records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        svc = self.service
        mapping = svc.mapping()
        keys = svc.schema.keys if svc.schema else []
        rows, invalid = [], 0
        for raw in raw_records:
            ts = parse_odata_datetime(raw.get(mapping["timestamp"]), svc.clock)
            if ts is None:
                invalid += 1
                continue
            dims = {}
            for role in DIMENSION_ROLES:
                field = mapping.get(role)
                value = raw.get(field) if field else None
                dims[role] = None if value is None or isinstance(value, bool) else str(value).strip() or None
            content = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str)
            rows.append({
                "record_key": record_identity(raw, keys, ts, dims),
                "production_ts": iso_utc(ts),
                **dims,
                "quantity": parse_number(raw.get(mapping["quantity"])) if mapping.get("quantity") else None,
                "raw_json": content,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest()[:32],
            })
        return rows, invalid

    def tick(self) -> float:
        """Run one cycle. Returns seconds until the next cycle."""
        delay = self._ensure_validated()
        if delay is not None:
            return delay
        svc = self.service
        now = self.clock()
        start, end, gaps = self.compute_window(now)
        mapping = svc.mapping()
        ts_prop = svc.schema.get(mapping["timestamp"])
        version = svc.schema.odata_version
        clauses = (FilterClause(ts_prop.name, "ge", odata_datetime_literal(start, ts_prop.edm_type, version)),
                   FilterClause(ts_prop.name, "lt", odata_datetime_literal(end, ts_prop.edm_type, version)))
        select: tuple[str, ...] = ()
        if svc.capability("select") == "ok":
            select = tuple(dict.fromkeys([*svc.schema.keys, *[v for v in mapping.values() if v]]))
        ordered = svc.capability("orderby_asc") == "ok"
        spec = QuerySpec(top=self.config.limits.MAX_RECORDS, select=select, filters=clauses,
                         orderby=(ts_prop.name, "asc") if ordered else None)
        run_id = self.db.start_run("collect", now)
        self.state["last_attempt_at"] = iso_utc(now)
        self.state["status"] = "querying"
        result = svc.client.query(spec, COLLECTOR_SESSION)
        common = dict(http_status=result.http_status, elapsed_ms=round(result.elapsed_ms, 1),
                      window_start=iso_utc(start), window_end=iso_utc(end), relative_url=result.relative_url)
        if not result.ok:
            self.db.finish_run(run_id, status=result.status.value, message=result.message,
                               error_detail=result.technical_detail[:500], **common)
            if result.status == Status.CIRCUIT_OPEN:
                self.state.update(status="backoff", message=result.message)
                return max(60.0, result.wait_seconds + 1)
            if result.status in LOCAL_REJECTIONS and result.status not in AUTH_ERRORS:
                self.state.update(status="waiting", message=result.message)
                return 60.0  # nothing was sent; retry shortly without counting a server failure
            if result.status in (Status.BAD_REQUEST, Status.NOT_FOUND):
                self._validated = False  # schema may have changed: re-validate (after backoff)
                self._metadata_ok = False
            return self._backoff(result.status.value, result.message, result.http_status,
                                 auth=result.status in AUTH_ERRORS)

        rows, invalid = self.normalize(result.records)
        counts = self.db.upsert_records(run_id, rows, svc.schema.schema_hash, now)
        full_page = result.more_available or len(result.records) >= spec.top
        newest = max((r["production_ts"] for r in rows), default=None)
        warnings: list[str] = []
        if full_page and ordered and newest:
            if newest == self.state.get("cursor") and self.state.get("catching_up"):
                warnings.append(f"Más de {spec.top} registros comparten la misma hora; no es posible avanzar sin aumentar MAX_RECORDS.")
                self.state["cursor"] = iso_utc(datetime.fromisoformat(newest) + timedelta(seconds=1))
                gaps.append({"from": newest, "to": self.state["cursor"], "reason": "Registros con la misma hora superan $top."})
            else:
                self.state["cursor"] = newest
            self.state["catching_up"] = True
        else:
            if full_page:
                warnings.append(f"La ventana tenía más de {spec.top} registros y el orden ascendente no está comprobado: "
                                "pueden faltar registros de esta ventana.")
                gaps.append({"from": iso_utc(start), "to": iso_utc(end), "reason": "Página completa sin orden verificado."})
            current_cursor = datetime.fromisoformat(self.state["cursor"]) if self.state.get("cursor") else start
            self.state["cursor"] = iso_utc(max(current_cursor, datetime.fromisoformat(newest)) if newest else max(current_cursor, start))
            self.state["catching_up"] = False
        if invalid:
            warnings.append(f"{invalid} registro(s) sin fecha válida fueron descartados.")
        if gaps:
            self.state["gaps"] = (self.state.get("gaps", []) + gaps)[-10:]
        if not self.state.get("coverage_start") or iso_utc(start) < self.state["coverage_start"]:
            self.state["coverage_start"] = iso_utc(start)
        monitor = svc.monitor_metrics(now=now)
        source_note = "Lectura correcta (simulador DEMO)." if self.config.is_demo else "Lectura correcta de FactoryLogix."
        self.db.finish_run(run_id, status="ok", message="; ".join(warnings) or source_note,
                           records_received=len(result.records), truncated=int(full_page),
                           metrics_json=live_metrics.run_snapshot(monitor), **counts, **common)
        self.state.update(status="ok", consecutive_failures=0, last_success_at=iso_utc(now), last_error=None,
                          message=("Sincronizando historial: se continuará en el siguiente ciclo." if self.state["catching_up"]
                                   else "Lectura correcta."), warnings=self.state.get("warnings", [])[:1] + warnings)
        self._persist()
        self.db.cleanup_collector(self.settings.record_retention_days)
        logger.info("collector ok window=%s..%s received=%d new=%d updated=%d same=%d catching_up=%s",
                    iso_utc(start), iso_utc(end), len(result.records), counts["inserted"], counts["updated"],
                    counts["unchanged"], self.state["catching_up"])
        return float(self.settings.interval_seconds)

    def snapshot(self) -> dict[str, Any]:
        data = dict(self.state)
        data["running"] = bool(self._thread and self._thread.is_alive())
        return data
