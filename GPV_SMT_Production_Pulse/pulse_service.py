"""Application service layer: orchestrates validation, cache, OData client and analytics.

Query pipeline (``run_query``):
1. Validate and normalize browser parameters (dates, filters, interval).
2. Refuse filters that are not confirmed (never show/accept a functionally false filter).
3. Serve a fresh cache entry if one exists (shared by every local user).
4. Check readiness: schema loaded, timestamp+quantity mapped, ``$top`` and date filter tested OK.
   If not ready the query is BLOCKED with an explanation; it is never replaced by an
   unfiltered query.
5. Issue ONE bounded GET through ``ODataClient`` (single-flight, limits, breaker).
6. On success store in cache and analyze. On failure return the error plus a pointer to the
   last stored data (clearly labelled as stored, never as live).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import analytics
import live_metrics
from capability_probe import PROBE_LABELS_ES, PROBE_ORDER, binding_hash, probes_to_json, run_probes, was_aborted
from database import Database, signature_for
from metadata_inspector import (EntitySchema, MetadataError, ROLE_LABELS_ES, availability_report,
                                best_guess_mapping, load_saved_schema, parse_metadata, save_schema,
                                suggest_roles, validate_mapping)
from odata_client import FilterClause, MESSAGES_ES, ODataClient, QuerySpec, Status
from report_generator import build_snapshot
from security import (ValidationError, odata_datetime_literal, odata_value_literal, validate_date,
                      validate_filter_value, validate_interval)
from settings import ALLOWED_ENTITY_SET, APP_NAME, APP_VERSION, FIELD_ROLES, Config
from timeutil import PlantClock, format_duration_es, iso_utc, utc_now

logger = logging.getLogger("pulse.service")

FILTER_ROLES = ("line", "station", "shift")


@dataclass(frozen=True)
class NormalizedQuery:
    start: date
    end: date
    line: str | None
    station: str | None
    shift: str | None
    interval: str

    @property
    def filters(self) -> dict[str, str | None]:
        return {"line": self.line, "station": self.station, "shift": self.shift}

    def shifted_previous(self) -> "NormalizedQuery":
        days = (self.end - self.start).days + 1
        return NormalizedQuery(self.start - timedelta(days=days), self.start - timedelta(days=1),
                               self.line, self.station, self.shift, self.interval)


class PulseService:
    """Business logic shared by the HTTP layer and the tests."""

    def __init__(self, config: Config, db: Database, client: ODataClient, clock: PlantClock | None = None) -> None:
        self.config = config
        self.db = db
        self.client = client
        self.clock = clock or PlantClock(config.analytics.plant_timezone)
        self.schema: EntitySchema | None = None
        self.metadata_state: dict[str, Any] = {"status": "not_checked", "message": "Metadata aún no verificada."}
        self._last_metadata_check: float | None = None
        self._last_probe_run: float | None = None
        self._admin_lock = threading.Lock()
        self._writes_since_cleanup = 0
        self.collector: Any = None  # set by app.main() when the background collector runs

    @property
    def collector_mode(self) -> bool:
        """With the collector running, every screen reads SQLite only (no per-user OData requests)."""
        return self.collector is not None

    # ------------------------------------------------------------------ lifecycle
    @property
    def data_mode(self) -> str:
        return "demo" if self.config.is_demo else "live"

    def startup(self) -> None:
        """Load persisted state; in DEMO mode prepare the simulator automatically."""
        self.cleanup()
        self.schema = load_saved_schema(self.config.metadata_dir)
        if self.schema:
            self.metadata_state = {"status": "loaded", "message": "Esquema validado cargado desde copia local.",
                                   "retrieved_at": self.schema.retrieved_at}
        if self.config.is_demo:
            if self.schema is None:
                self.check_connection("demo-startup", force=True)
            if self.schema and not self.db.get_setting("field_mapping"):
                from demo_source import DEMO_MAPPING

                self.db.set_setting("field_mapping", dict(DEMO_MAPPING))
                self.db.set_setting("field_mapping_source", "demo")
            if self.schema and not self._valid_probes():
                self.run_capability_probes("demo-startup", force=True, delay=0)
        self.db.set_setting("effective_limits", self.config.public_limits())
        logger.info("service started mode=%s schema=%s", self.data_mode, bool(self.schema))

    def cleanup(self) -> dict[str, int]:
        r = self.config.retention
        removed = self.db.cleanup(cache_retention_days=r.CACHE_RETENTION_DAYS,
                                  history_retention_days=r.HISTORY_RETENTION_DAYS,
                                  report_retention_days=r.REPORT_RETENTION_DAYS,
                                  max_db_size_mb=r.MAX_DB_SIZE_MB)
        self._writes_since_cleanup = 0
        return removed

    # ------------------------------------------------------------------ mapping & capabilities
    def mapping(self) -> dict[str, str | None]:
        """Effective confirmed mapping (UI-confirmed in DB, else config.json), validated against schema."""
        stored = self.db.get_setting("field_mapping")
        source = stored if isinstance(stored, dict) else self.config.field_mapping
        if not self.schema:
            return {role: None for role in FIELD_ROLES}
        clean, _ = validate_mapping(self.schema, {r: source.get(r) for r in FIELD_ROLES})
        return clean

    def mapping_source(self) -> str:
        """confirmed (UI) | config (config.json) | auto (name detection, unconfirmed) | demo | none."""
        if self.db.get_setting("field_mapping"):
            return self.db.get_setting("field_mapping_source") or "confirmed"
        return "config" if any(self.config.field_mapping.values()) else "none"

    def _valid_probes(self) -> dict[str, dict[str, Any]]:
        stored = self.db.get_setting("probes")
        if not self.schema or not isinstance(stored, dict):
            return {}
        if stored.get("binding") != binding_hash(self.schema, self.mapping()):
            return {}
        return stored.get("results", {})

    def capability(self, name: str) -> str:
        return self._valid_probes().get(name, {}).get("status", "not_tested")

    def available_filters(self) -> dict[str, Any]:
        mapping = self.mapping()
        filters = {"date": self.capability("filter_date") == "ok"}
        for role in FILTER_ROLES:
            if self.collector_mode:
                # Local filtering over stored records: no OData filter is sent for these.
                filters[role] = bool(mapping.get(role))
            else:
                filters[role] = bool(mapping.get(role)) and self.capability(f"filter_{role}") == "ok"
        intervals = ["hour", "day"] + (["shift"] if mapping.get("shift") else [])
        return {"filters": filters, "intervals": intervals}

    def readiness(self) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        mapping = self.mapping()
        if not self.schema:
            reasons.append("La metadata de ProductivityOverTime no ha sido validada. Usa 'Verificar conexión'.")
        else:
            if not mapping.get("timestamp"):
                reasons.append("No se ha confirmado el campo de fecha/hora.")
            if not mapping.get("quantity"):
                reasons.append("No se ha confirmado el campo de cantidad producida.")
            if self.capability("top") != "ok":
                reasons.append("No se ha comprobado que el servidor respete el límite de registros ($top).")
            if self.capability("filter_date") != "ok":
                reasons.append("No se ha comprobado que el servidor permita filtrar por fecha.")
        return not reasons, reasons

    # ------------------------------------------------------------------ query validation
    def normalize_query(self, body: dict[str, Any]) -> NormalizedQuery:
        if not isinstance(body, dict):
            raise ValidationError("Solicitud no válida.")
        start = validate_date(body.get("start", ""), "fecha inicial")
        end = validate_date(body.get("end", ""), "fecha final")
        today = self.clock.now().date()
        if end < start:
            raise ValidationError("La fecha final no puede ser anterior a la fecha inicial.")
        if start > today:
            raise ValidationError("La fecha inicial no puede estar en el futuro.")
        if (end - start).days + 1 > self.config.limits.MAX_QUERY_RANGE_DAYS:
            raise ValidationError(f"El periodo máximo permitido es de {self.config.limits.MAX_QUERY_RANGE_DAYS} días.")
        available = self.available_filters()
        values: dict[str, str | None] = {}
        for role in FILTER_ROLES:
            raw = body.get(role)
            if raw in (None, ""):
                values[role] = None
                continue
            if not available["filters"][role]:
                raise ValidationError(f"El filtro de {ROLE_LABELS_ES[role].lower()} no está disponible: "
                                      "no se ha comprobado su compatibilidad con FactoryLogix.")
            values[role] = validate_filter_value(str(raw))
        interval = validate_interval(body.get("interval"))
        if interval not in available["intervals"]:
            raise ValidationError("El intervalo por turno requiere un campo de turno confirmado.")
        return NormalizedQuery(start, end, values["line"], values["station"], values["shift"], interval)

    def _params(self, nq: NormalizedQuery) -> dict[str, Any]:
        return {"data_mode": self.data_mode, "entity": ALLOWED_ENTITY_SET, "start": nq.start.isoformat(),
                "end": nq.end.isoformat(), **nq.filters,
                "schema": self.schema.schema_hash if self.schema else None, "mapping": self.mapping()}

    def build_spec(self, nq: NormalizedQuery) -> QuerySpec:
        """Build the bounded query. Only tested options are used."""
        assert self.schema is not None
        mapping = self.mapping()
        ts = self.schema.get(mapping["timestamp"])
        assert ts is not None
        start, end = self.clock.period_bounds(nq.start, nq.end)
        clauses = [
            FilterClause(ts.name, "ge", odata_datetime_literal(start, ts.edm_type, self.schema.odata_version)),
            FilterClause(ts.name, "lt", odata_datetime_literal(end, ts.edm_type, self.schema.odata_version)),
        ]
        for role, value in nq.filters.items():
            if value is None:
                continue
            prop = self.schema.get(mapping[role])
            assert prop is not None
            clauses.append(FilterClause(prop.name, "eq", odata_value_literal(value, prop.edm_type)))
        select: tuple[str, ...] = ()
        if self.capability("select") == "ok":
            select = tuple(dict.fromkeys([*self.schema.keys, *[v for v in mapping.values() if v]]))
        orderby = (ts.name, "desc") if self.capability("orderby") == "ok" else None
        return QuerySpec(top=self.config.limits.MAX_RECORDS, select=select, filters=tuple(clauses), orderby=orderby)

    # ------------------------------------------------------------------ queries
    def run_query(self, body: dict[str, Any], session_id: str) -> dict[str, Any]:
        """Execute the operator query flow. Never raises for expected conditions."""
        if self.collector_mode:
            return self.local_query(body)
        try:
            nq = self.normalize_query(body)
        except ValidationError as exc:
            return self._error("invalid_input", str(exc))
        if body.get("auto") and not self.config.limits.AUTO_REFRESH_ENABLED:
            return self._error("auto_refresh_disabled", "La actualización automática está deshabilitada por configuración.")
        force = bool(body.get("force_refresh"))
        params = self._params(nq)
        signature = signature_for(params)
        cached = self.db.get_cache(signature)

        if cached and cached["is_fresh"] and not force:
            self.db.add_history(kind="query", query_text=cached["relative_url"], result_status="ok",
                                cache_status="hit", record_count=cached["record_count"])
            return self._result_from_cache(cached, nq, "cache")
        if cached and force and cached["age_seconds"] < self.config.limits.MIN_REFRESH_INTERVAL_SECONDS:
            wait = self.config.limits.MIN_REFRESH_INTERVAL_SECONDS - cached["age_seconds"]
            result = self._result_from_cache(cached, nq, "cache")
            result["notice"] = (f"Los datos se actualizaron hace {format_duration_es(cached['age_seconds'])}. "
                                f"Podrás forzar otra actualización en {int(wait) + 1} s.")
            return result

        ready, reasons = self.readiness()
        if not ready:
            self.db.add_history(kind="query", query_text=f"{nq.start}..{nq.end}", result_status="blocked_unverified",
                                cache_status="blocked", error_detail="; ".join(reasons))
            return self._error(Status.BLOCKED_UNVERIFIED.value, MESSAGES_ES[Status.BLOCKED_UNVERIFIED],
                               reasons=reasons, stored=cached)
        try:
            spec = self.build_spec(nq)
        except ValidationError as exc:
            return self._error("invalid_input", str(exc))
        result = self.client.query(spec, session_id)
        if not result.reached_server:
            self.db.add_history(kind="query", query_text=result.relative_url or f"{nq.start}..{nq.end}",
                                result_status=result.status.value, cache_status="blocked")
            return self._error(result.status.value, result.message, wait_seconds=result.wait_seconds, stored=cached)
        self.db.add_history(kind="query", query_text=result.relative_url, result_status=result.status.value,
                            cache_status="miss", response_ms=round(result.elapsed_ms, 1),
                            record_count=len(result.records), http_status=result.http_status,
                            error_detail=result.technical_detail if not result.ok else None)
        if not result.ok:
            return self._error(result.status.value, result.message, stored=cached, http_status=result.http_status)
        cache_id = self.db.put_cache(
            signature=signature, query_params=params, relative_url=result.relative_url, records=result.records,
            ttl_seconds=self.config.limits.CACHE_TTL_SECONDS,
            more_available=result.more_available or len(result.records) >= spec.top,
            validation_state="tested_filters", schema_hash=self.schema.schema_hash if self.schema else "",
        )
        self._writes_since_cleanup += 1
        if self._writes_since_cleanup >= 50:
            self.cleanup()
        entry = self.db.get_cache_by_id(cache_id)
        assert entry is not None
        out = self._result_from_cache(entry, nq, "odata")
        if result.top_ignored:
            out["warnings"].append("El servidor devolvió más registros de los solicitados; se conservaron solo los permitidos.")
        return out

    def last_query(self) -> dict[str, Any]:
        """Most recent stored result. Never contacts FactoryLogix."""
        entry = self.db.latest_cache()
        if not entry:
            return self._error("no_stored_data", "Todavía no hay consultas guardadas en este equipo.")
        return self._from_entry(entry, interval=None)

    def stored_result(self, cache_id: int, interval: str | None = None) -> dict[str, Any]:
        entry = self.db.get_cache_by_id(cache_id)
        if not entry:
            return self._error("not_found", "La información guardada ya no existe (política de retención).")
        return self._from_entry(entry, interval)

    def _from_entry(self, entry: dict[str, Any], interval: str | None) -> dict[str, Any]:
        p = entry["query_params"]
        try:
            interval = validate_interval(interval) if interval else "hour"
        except ValidationError:
            interval = "hour"
        nq = NormalizedQuery(date.fromisoformat(p["start"]), date.fromisoformat(p["end"]),
                             p.get("line"), p.get("station"), p.get("shift"), interval)
        return self._result_from_cache(entry, nq, "cache" if entry["is_fresh"] else "stored",
                                       mapping=p.get("mapping"))

    def _analyze(self, entry: dict[str, Any], nq: NormalizedQuery, from_cache: bool,
                 mapping: dict[str, str | None]) -> dict[str, Any]:
        start, end = self.clock.period_bounds(nq.start, nq.end)
        a = self.config.analytics
        return analytics.analyze(entry["records"], mapping=mapping, clock=self.clock, period_start=start,
                                 period_end=end, interval=nq.interval, truncated=entry["more_available"],
                                 fetched_at=entry["fetched_at"], from_cache=from_cache,
                                 unit_label=a.quantity_unit_label, drop_threshold_percent=a.drop_threshold_percent,
                                 min_buckets_for_drop=a.min_buckets_for_drop_detection)

    def _result_from_cache(self, entry: dict[str, Any], nq: NormalizedQuery, source: str,
                           mapping: dict[str, str | None] | None = None) -> dict[str, Any]:
        mapping = mapping or entry["query_params"].get("mapping") or self.mapping()
        from_cache = source != "odata"
        result_analytics = self._analyze(entry, nq, from_cache, mapping)
        previous_nq = nq.shifted_previous()
        prev_params = dict(entry["query_params"], start=previous_nq.start.isoformat(), end=previous_nq.end.isoformat())
        prev_entry = self.db.get_cache(signature_for(prev_params))
        prev_analytics = self._analyze(prev_entry, previous_nq, True, mapping) if prev_entry else None
        trend = analytics.trend(result_analytics, prev_analytics, prev_entry["fetched_at"] if prev_entry else None)
        trend["previous_period"] = {"start": previous_nq.start.isoformat(), "end": previous_nq.end.isoformat()}
        origin = "al simulador DEMO" if self.config.is_demo else "a FactoryLogix"
        messages = {"odata": f"Datos disponibles: consulta directa {origin}.",
                    "cache": "Información desde caché (vigente).",
                    "stored": "Información guardada: NO es información actual."}
        warnings: list[str] = []
        if entry["more_available"]:
            warnings.append(f"Se alcanzó el límite de {self.config.limits.MAX_RECORDS} registros o el servidor tiene más "
                            "páginas: el resultado es parcial. Reduce el periodo o aplica filtros.")
        if source == "stored":
            warnings.append(f"Esta información fue extraída hace {format_duration_es(entry['age_seconds'])} y puede no "
                            "reflejar la producción actual.")
        return {
            "ok": True,
            "status": "ok" if result_analytics["records_used"] else "no_records",
            "source": source,
            "message": messages[source] if result_analytics["records_used"] else analytics.NO_DATA_MESSAGE,
            "data_mode": self.data_mode,
            "cache_id": entry["id"],
            "fetched_at": entry["fetched_at"],
            "age_seconds": round(entry["age_seconds"]),
            "is_fresh": entry["is_fresh"],
            "more_available": entry["more_available"],
            "relative_url": entry["relative_url"],
            "query": {"period": {"start": nq.start.isoformat(), "end": nq.end.isoformat()},
                      "filters": nq.filters, "interval": result_analytics["interval"]},
            "mapping": mapping,
            "analytics": result_analytics,
            "trend": trend,
            "rows": analytics.display_rows(entry["records"], mapping, self.clock),
            "warnings": warnings,
        }

    def _error(self, status: str, message: str, *, reasons: list[str] | None = None,
               stored: dict[str, Any] | None = None, wait_seconds: float = 0.0,
               http_status: int | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "status": status, "message": message, "reasons": reasons or [],
                               "wait_seconds": round(wait_seconds), "http_status": http_status,
                               "data_mode": self.data_mode, "stored_available": False}
        latest = stored or self.db.latest_cache()
        if latest:
            out.update(stored_available=True, stored_cache_id=latest["id"], stored_fetched_at=latest["fetched_at"])
        return out

    # ------------------------------------------------------------------ diagnostics / admin
    def check_connection(self, session_id: str, force: bool = False) -> dict[str, Any]:
        """Low-cost check: one GET to $metadata (bounded size), parse and persist the schema."""
        with self._admin_lock:
            now = time.monotonic()
            interval = self.config.limits.MIN_METADATA_CHECK_INTERVAL_SECONDS
            if not force and self._last_metadata_check is not None and now - self._last_metadata_check < interval:
                wait = interval - (now - self._last_metadata_check)
                return {"ok": False, "status": "rate_limited",
                        "message": f"La conexión se verificó recientemente. Espera {int(wait) + 1} s.",
                        "diagnostics": self.diagnostics(session_id)}
            self._last_metadata_check = now
            result = self.client.fetch_metadata(session_id)
            self.db.add_history(kind="metadata", query_text="$metadata", result_status=result.status.value,
                                cache_status="miss" if result.reached_server else "blocked",
                                response_ms=round(result.elapsed_ms, 1), http_status=result.http_status,
                                error_detail=result.technical_detail if not result.ok else None)
            if not result.ok or result.body is None:
                self.metadata_state = {"status": result.status.value, "message": result.message,
                                       "checked_at": iso_utc(utc_now())}
                return {"ok": False, "status": result.status.value, "message": result.message,
                        "diagnostics": self.diagnostics(session_id)}
            source = "examples/metadata_sample.xml (SIMULADO)" if self.config.is_demo else self.config.odata.base_url + "$metadata"
            try:
                schema = parse_metadata(result.body, source=source)
            except MetadataError as exc:
                self.metadata_state = {"status": Status.METADATA_INCOMPATIBLE.value,
                                       "message": f"{MESSAGES_ES[Status.METADATA_INCOMPATIBLE]} {exc.message}",
                                       "checked_at": iso_utc(utc_now())}
                return {"ok": False, "status": Status.METADATA_INCOMPATIBLE.value,
                        "message": self.metadata_state["message"], "diagnostics": self.diagnostics(session_id)}
            changed = self.schema is not None and self.schema.schema_hash != schema.schema_hash
            save_schema(schema, result.body, self.config.metadata_dir)
            self.schema = schema
            self.metadata_state = {"status": "ok", "checked_at": iso_utc(utc_now()), "retrieved_at": schema.retrieved_at,
                                   "message": "Metadata validada: ProductivityOverTime identificado."}
            if changed:
                self.metadata_state["message"] += " El esquema cambió: las pruebas de compatibilidad previas ya no aplican."
            return {"ok": True, "status": "ok", "message": self.connection_summary(),
                    "diagnostics": self.diagnostics(session_id)}

    def connection_summary(self) -> str:
        if not self.schema:
            return "No se ha validado la metadata."
        server = "El simulador DEMO" if self.config.is_demo else "FactoryLogix"
        if self.capability("filter_date") == "ok":
            return f"{server} respondió y el filtro por fecha está comprobado."
        return f"{server} respondió, pero todavía no se ha comprobado que permita filtrar por fecha."

    def save_mapping(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self.schema:
            return {"ok": False, "message": "Primero valida la metadata con 'Verificar conexión'."}
        if not isinstance(body, dict):
            return {"ok": False, "message": "Solicitud no válida."}
        requested = {role: (body.get(role) or None) for role in FIELD_ROLES}
        for role, value in requested.items():
            if value is not None and not isinstance(value, str):
                return {"ok": False, "message": f"Valor no válido para {ROLE_LABELS_ES[role]}."}
        clean, errors = validate_mapping(self.schema, requested)
        if errors:
            return {"ok": False, "message": " ".join(errors)}
        self.db.set_setting("field_mapping", clean)
        self.db.set_setting("field_mapping_source", "confirmed")
        logger.info("field mapping confirmed: %s", clean)
        return {"ok": True, "message": "Mapeo de campos confirmado. Ejecuta 'Probar compatibilidad' para validar filtros.",
                "mapping": clean}

    def run_capability_probes(self, session_id: str, force: bool = False, delay: float | None = None) -> dict[str, Any]:
        with self._admin_lock:
            if not self.schema:
                return {"ok": False, "message": "Primero valida la metadata con 'Verificar conexión'."}
            now = time.monotonic()
            interval = self.config.limits.MIN_PROBE_INTERVAL_SECONDS
            if not force and self._last_probe_run is not None and now - self._last_probe_run < interval:
                wait = interval - (now - self._last_probe_run)
                return {"ok": False, "message": f"Las pruebas se ejecutaron recientemente. Espera {int(wait) + 1} s."}
            self._last_probe_run = now
            mapping = self.mapping()
            results = run_probes(self.client, self.schema, mapping, session_id, self.clock,
                                 delay_seconds=self.config.limits.PROBE_DELAY_SECONDS if delay is None else delay)
            for r in results.values():
                if r.query:
                    self.db.add_history(kind="probe", query_text=r.query, result_status=r.status,
                                        cache_status="miss", http_status=r.http_status, error_detail=r.detail)
            if was_aborted(results):
                # Server/auth failure: these results are not evidence; nothing is stored.
                reason = next(r.detail for r in results.values() if r.detail.startswith("Secuencia detenida"))
                return {"ok": False, "status": "probes_aborted", "message": reason, "summary": self.connection_summary()}
            self.db.set_setting("probes", {"binding": binding_hash(self.schema, mapping),
                                           "executed_at": iso_utc(utc_now()), "results": probes_to_json(results)})
            ok_count = sum(1 for r in results.values() if r.status == "ok")
            return {"ok": True, "message": f"Pruebas completadas: {ok_count} de {len(results)} opciones comprobadas.",
                    "summary": self.connection_summary()}

    def diagnostics(self, session_id: str | None = None) -> dict[str, Any]:
        probes = self._valid_probes()
        stored_probes = self.db.get_setting("probes") or {}
        ready, reasons = self.readiness()
        schema = self.schema
        caps = schema.capabilities if schema else None
        return {
            "data_mode": self.data_mode,
            "server": "Simulador local (modo DEMO)" if self.config.is_demo else self.config.odata.base_url,
            "auth_mode": self.config.odata.auth_mode,
            "metadata": self.metadata_state,
            "summary": self.connection_summary(),
            "entity": {
                "name": ALLOWED_ENTITY_SET,
                "compatible": schema is not None,
                "entity_type": schema.entity_type if schema else None,
                "odata_version": schema.odata_version if schema else None,
                "schema_hash": schema.schema_hash if schema else None,
                "keys": schema.keys if schema else [],
                "properties": [p.__dict__ for p in schema.properties] if schema else [],
                "navigation_properties": schema.navigation_properties if schema else [],
                "warnings": schema.warnings if schema else [],
                "announced": ({"top_supported": caps.top_supported, "filterable": caps.filterable,
                               "sortable": caps.sortable, "select_supported": caps.select_supported,
                               "non_filterable": caps.non_filterable_properties,
                               "terms": caps.terms_found} if caps else None),
            },
            "roles": availability_report(schema, self.mapping()),
            "role_options": suggest_roles(schema) if schema else {},
            "suggested_mapping": best_guess_mapping(schema) if schema else {},
            "mapping": self.mapping(),
            "probes": [probes.get(name) or {"name": name, "label": PROBE_LABELS_ES[name], "status": "not_tested",
                                            "detail": "Sin prueba vigente."} for name in PROBE_ORDER],
            "probes_executed_at": stored_probes.get("executed_at") if probes else None,
            "ready": ready,
            "readiness_reasons": reasons,
            "client": self.client.snapshot(),
            "usage": self.client.gate.usage(session_id),
            "cache": self.db.stats(),
            "history": self.db.list_history(15),
            "limits": self.config.public_limits(),
            "auth": getattr(self.client, "auth_description", "—"),
            "mapping_source": self.mapping_source(),
            "collector": self.collector.snapshot() if self.collector else None,
            "collector_runs": self.db.list_runs(15),
            "records": self.db.record_stats(),
        }

    def status(self, session_id: str | None = None) -> dict[str, Any]:
        """Lightweight status for every page load (no network)."""
        ready, reasons = self.readiness()
        mapping = self.mapping()
        if self.collector_mode:
            known = {role: self.db.distinct_values(role) if mapping.get(role) else [] for role in FILTER_ROLES}
        else:
            known = {role: self.db.known_values(mapping[role]) if mapping.get(role) else [] for role in FILTER_ROLES}
        latest = self.db.latest_cache()
        return {
            "app": APP_NAME, "version": APP_VERSION, "data_mode": self.data_mode,
            "ready": ready, "readiness_reasons": reasons,
            "available": self.available_filters(), "known_values": known,
            "mapping": mapping,
            "limits": {k: v for k, v in self.config.public_limits().items()
                       if k in ("MAX_RECORDS", "CACHE_TTL_SECONDS", "MIN_REFRESH_INTERVAL_SECONDS",
                                "AUTO_REFRESH_ENABLED", "AUTO_REFRESH_INTERVAL_SECONDS", "MAX_QUERY_RANGE_DAYS",
                                "REQUEST_TIMEOUT_SECONDS")},
            "today": self.clock.now().date().isoformat(),
            "timezone": self.clock.zone_name,
            "breaker": self.client.breaker.snapshot(),
            "busy": self.client.gate.is_busy(),
            "latest_stored": ({"cache_id": latest["id"], "fetched_at": latest["fetched_at"]} if latest else None),
            "collector_mode": self.collector_mode,
            "mapping_source": self.mapping_source(),
            "poll_seconds": self.config.collector.dashboard_poll_seconds,
        }

    # ------------------------------------------------------------------ reports & trends
    def create_report(self, body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict):
            return {"ok": False, "message": "Solicitud no válida."}
        if isinstance(body.get("local_query"), dict):
            result = self.local_query(body["local_query"])
            if not result.get("ok"):
                return {"ok": False, "message": result["message"]}
            snapshot = build_snapshot(result, iso_utc(utc_now()))
            report_id = self.db.save_report(
                period_start=result["query"]["period"]["start"], period_end=result["query"]["period"]["end"],
                filters=result["query"]["filters"], data_source="local", data_fetched_at=result["fetched_at"] or "",
                from_cache=True, snapshot=snapshot)
            return {"ok": True, "report_id": report_id, "message": "Reporte generado."}
        try:
            cache_id = int(body.get("cache_id"))
        except (TypeError, ValueError):
            return {"ok": False, "message": "Primero realiza o abre una consulta."}
        interval = body.get("interval")
        result = self.stored_result(cache_id, interval if isinstance(interval, str) else None)
        if not result.get("ok"):
            return {"ok": False, "message": result["message"]}
        # The browser reports how the operator obtained this data (direct OData query or cache).
        # It can only downgrade "odata" to a cache source, never claim fresher data than stored.
        if body.get("viewed_source") == "odata" and result["source"] == "cache" and result["age_seconds"] <= self.config.limits.CACHE_TTL_SECONDS:
            result["source"] = "odata"
        snapshot = build_snapshot(result, iso_utc(utc_now()))
        report_id = self.db.save_report(
            period_start=result["query"]["period"]["start"], period_end=result["query"]["period"]["end"],
            filters=result["query"]["filters"], data_source=result["source"], data_fetched_at=result["fetched_at"],
            from_cache=result["source"] != "odata", snapshot=snapshot,
        )
        return {"ok": True, "report_id": report_id, "message": "Reporte generado."}

    def stored_list(self) -> list[dict[str, Any]]:
        rows = []
        for item in self.db.list_cache(60):
            p = item["query_params"]
            rows.append({"cache_id": item["id"], "start": p["start"], "end": p["end"],
                         "filters": {r: p.get(r) for r in FILTER_ROLES}, "fetched_at": item["fetched_at"],
                         "records": item["record_count"], "partial": item["more_available"],
                         "is_fresh": item["is_fresh"], "age": format_duration_es(item["age_seconds"])})
        return rows

    def compare(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            a_id, b_id = int(body.get("a")), int(body.get("b"))
        except (TypeError, ValueError, AttributeError):
            return {"ok": False, "message": "Selecciona dos consultas guardadas."}
        interval = body.get("interval") if isinstance(body.get("interval"), str) else None
        a, b = self.stored_result(a_id, interval), self.stored_result(b_id, interval)
        if not a.get("ok") or not b.get("ok"):
            return {"ok": False, "message": "Una de las consultas guardadas ya no existe."}
        return {"ok": True, "a": a, "b": b,
                "comparison": analytics.compare_snapshots(a["analytics"], b["analytics"])}

    # ------------------------------------------------------------------ collector mode (local data only)
    def _collector_state(self) -> dict[str, Any]:
        if self.collector is not None:
            return self.collector.snapshot()
        return self.db.get_setting("collector_state") or {}

    def local_query(self, body: dict[str, Any]) -> dict[str, Any]:
        """Analyze stored collector records for a period. Never contacts FactoryLogix."""
        try:
            nq = self.normalize_query(body)
        except ValidationError as exc:
            return self._error("invalid_input", str(exc))
        return self._local_result(nq)

    def _local_analysis(self, nq: NormalizedQuery) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        mapping = self.mapping()
        start, end = self.clock.period_bounds(nq.start, nq.end)
        filters = {k: v for k, v in nq.filters.items() if v}
        rows = self.db.query_records(iso_utc(start - timedelta(hours=24)), iso_utc(end), filters)
        sem = live_metrics.resolve_semantics(self.config.collector.quantity_semantics, rows, mapping)
        raw_records = []
        for row, inc in live_metrics.increments(rows, sem["semantics"], mapping):
            ts = datetime.fromisoformat(row["production_ts"])
            if not start <= ts < end:
                continue
            raw = json.loads(row["raw_json"])
            if mapping.get("quantity"):
                raw[mapping["quantity"]] = inc
            raw_records.append(raw)
        state = self._collector_state()
        coverage_start = state.get("coverage_start")
        partial = bool(state.get("catching_up"))
        warnings: list[str] = []
        if coverage_start and datetime.fromisoformat(coverage_start) > start:
            partial = True
            warnings.append(f"La información local comienza en {coverage_start} (UTC); antes no hay lecturas guardadas.")
        for gap in state.get("gaps", []):
            if datetime.fromisoformat(gap["from"]) < end and datetime.fromisoformat(gap["to"]) > start:
                partial = True
                warnings.append(f"Periodo sin lectura completa: {gap['from']} – {gap['to']} ({gap['reason']})")
        if state.get("catching_up"):
            warnings.append("El recolector aún está recuperando historial; el resultado puede estar incompleto.")
        if sem["semantics"] == "undetermined" and mapping.get("quantity"):
            warnings.append("Semántica de la cantidad indeterminada (intervalo o acumulado): no se suman unidades. " + sem["reason"])
        # Buckets after the point where local data is complete count as "in progress" (no drops, no trend).
        complete_until = utc_now()
        if state.get("catching_up") and state.get("cursor"):
            complete_until = datetime.fromisoformat(state["cursor"])
        elif state.get("last_success_at"):
            complete_until = min(complete_until, datetime.fromisoformat(state["last_success_at"]))
        a = self.config.analytics
        result_analytics = analytics.analyze(
            raw_records, mapping=mapping, clock=self.clock, period_start=start, period_end=end, interval=nq.interval,
            truncated=partial, fetched_at=state.get("last_success_at") or "", from_cache=True,
            unit_label=a.quantity_unit_label, drop_threshold_percent=a.drop_threshold_percent,
            min_buckets_for_drop=a.min_buckets_for_drop_detection, now=self.clock.to_local(complete_until))
        local_texts = {
            "La respuesta alcanzó": "La cobertura local del periodo está incompleta (ver advertencias); los totales corresponden "
                                     "solo a los registros guardados (resultado parcial).",
            "Información obtenida de la caché local": "Información del almacenamiento local del recolector; ver hora de la "
                                                       "última lectura.",
        }
        result_analytics["limitations"] = [next((v for k, v in local_texts.items() if t.startswith(k)), t)
                                           for t in result_analytics["limitations"]]
        for card in result_analytics["cards"]:
            if card["id"] == "updated":
                card["title"] = "Última lectura del recolector"
                card["note"] = "Hora de consulta a FactoryLogix (no hora de producción)"
        result_analytics["semantics"] = sem
        if sem["semantics"] == "cumulative":
            result_analytics["limitations"].insert(0, "Cantidad tratada como contador acumulado: la producción es la diferencia "
                                                      "entre lecturas consecutivas de cada línea/estación.")
        return result_analytics, raw_records, {"warnings": warnings, "partial": partial, "state": state}

    def _local_result(self, nq: NormalizedQuery) -> dict[str, Any]:
        mapping = self.mapping()
        result_analytics, raw_records, info = self._local_analysis(nq)
        prev_nq = nq.shifted_previous()
        prev_analytics, prev_raw, _ = self._local_analysis(prev_nq)
        trend = analytics.trend(result_analytics, prev_analytics if prev_raw else None,
                                info["state"].get("last_success_at") if prev_raw else None)
        trend["previous_period"] = {"start": prev_nq.start.isoformat(), "end": prev_nq.end.isoformat()}
        last_success = info["state"].get("last_success_at")
        age = (utc_now() - datetime.fromisoformat(last_success)).total_seconds() if last_success else None
        used = result_analytics["records_used"]
        return {
            "ok": True,
            "status": "ok" if used else "no_records",
            "source": "local",
            "message": ("Datos del almacenamiento local, actualizado por el recolector automático." if used
                        else analytics.NO_DATA_MESSAGE),
            "data_mode": self.data_mode,
            "cache_id": None,
            "fetched_at": last_success,
            "age_seconds": round(age) if age is not None else None,
            "is_fresh": age is not None and age <= self.config.collector.interval_seconds * 2,
            "more_available": info["partial"],
            "relative_url": "",
            "query": {"period": {"start": nq.start.isoformat(), "end": nq.end.isoformat()},
                      "filters": nq.filters, "interval": result_analytics["interval"]},
            "mapping": mapping,
            "analytics": result_analytics,
            "trend": trend,
            "rows": analytics.display_rows(raw_records, mapping, self.clock),
            "warnings": info["warnings"],
        }

    def compare_local(self, body: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(body, dict) or not isinstance(body.get("a"), dict) or not isinstance(body.get("b"), dict):
            return {"ok": False, "message": "Selecciona dos periodos."}
        extra = {k: body.get(k) for k in ("line", "interval") if body.get(k)}
        a = self.local_query({**body["a"], **extra})
        b = self.local_query({**body["b"], **extra})
        if not a.get("ok"):
            return {"ok": False, "message": a["message"]}
        if not b.get("ok"):
            return {"ok": False, "message": b["message"]}
        return {"ok": True, "a": a, "b": b, "comparison": analytics.compare_snapshots(a["analytics"], b["analytics"])}

    def monitor_metrics(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or utc_now()
        day_start = self.clock.day_start(self.clock.to_local(now).date())
        rows = self.db.query_records(iso_utc(day_start - timedelta(hours=24)), iso_utc(now + timedelta(hours=1)))
        return live_metrics.compute_monitor(
            rows, mapping=self.mapping(), semantics_config=self.config.collector.quantity_semantics, clock=self.clock,
            now=now, recent_minutes=self.config.collector.recent_activity_minutes,
            runs=self.db.successful_collects(2), collector_state=self._collector_state(),
            unit_label=self.config.analytics.quantity_unit_label)

    def monitor(self) -> dict[str, Any]:
        """Dashboard payload built only from SQLite and in-memory collector state."""
        state = self._collector_state()
        metrics = self.monitor_metrics()
        warnings: list[dict[str, str]] = []
        err = state.get("last_error")
        if err:
            last_ok = state.get("last_success_at")
            warnings.append({"kind": "error", "text": (
                f"Última consulta a FactoryLogix con error ({err.get('http_status') or err.get('status')}): {err.get('message')} "
                + (f"Se muestran los últimos datos guardados (última lectura correcta: {last_ok})." if last_ok
                   else "Todavía no hay lecturas correctas guardadas."))})
        if state.get("status") == "blocked":
            warnings.append({"kind": "error", "text": state.get("message", "Recolección bloqueada.")})
        if not self.collector_mode:
            warnings.append({"kind": "warn", "text": "El recolector automático no está en ejecución en este proceso; "
                                                     "los datos no se actualizarán."})
        if self.mapping_source() == "auto":
            warnings.append({"kind": "warn", "text": "Campos detectados automáticamente por nombre, pendientes de confirmar por "
                                                     "MES en 'Estado de conexión'."})
        if metrics["semantics"]["semantics"] == "undetermined" and metrics["quantity_field"]:
            warnings.append({"kind": "warn", "text": "No se pudo determinar si la cantidad es por intervalo o acumulada: "
                                                     + metrics["semantics"]["reason"]})
        elif metrics["semantics"].get("source") == "auto":
            warnings.append({"kind": "info", "text": "Semántica de cantidad detectada automáticamente: "
                                                     + metrics["semantics"]["label"] + ". Confirmar con MES y fijarla en config.json."})
        if state.get("catching_up"):
            warnings.append({"kind": "info", "text": "Sincronizando historial: el recolector recupera registros pendientes "
                                                     "(una consulta por ciclo)."})
        for text in state.get("warnings", []) or []:
            warnings.append({"kind": "warn", "text": text})
        return {"ok": True, "data_mode": self.data_mode, "app": APP_NAME, "version": APP_VERSION,
                "collector_mode": self.collector_mode, "collector": state, "metrics": metrics,
                "mapping": self.mapping(), "mapping_source": self.mapping_source(), "warnings": warnings,
                "poll_seconds": self.config.collector.dashboard_poll_seconds,
                "records": self.db.record_stats(), "runs": self.db.list_runs(10), "server_time": iso_utc(utc_now())}
