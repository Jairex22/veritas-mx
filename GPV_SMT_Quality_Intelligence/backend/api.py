"""Manejadores de la API JSON. Sin dependencias de HTTP: reciben dicts y devuelven dicts."""
from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from backend.config import APP_VERSION, ConfigError, public_config, resolve_path, validate_setting
from backend.credentials import credential_configured
from backend.security import InputError, validate_identifier
from models.entities import DATE_FIELD, KNOWN_ENTITIES
from models.query import Filter, QuerySpec
from reports.exporters import EXPORTERS
from reports.report_builder import build_unit_report
from services.pulse_service import PulseService
from services.quality_service import QualityService
from services.rework_service import ReworkService
from services.traceability_service import TraceabilityService

DIAG_WINDOWS = {"SMT": timedelta(hours=1), "Quality": timedelta(hours=24), "QualityHistory": timedelta(hours=24)}


class Api:
    def __init__(self, ctx):
        self.ctx = ctx

    # ------------------------------------------------------------- status
    def status(self, _body=None) -> dict:
        cfg = self.ctx.config
        policy = None
        if cfg["mode"] == "live":
            blocked = self.ctx.source.policy_check("*")
            policy = blocked.error if blocked else None
        return {
            "app": cfg["app"]["name"], "site": cfg["app"]["site"], "version": APP_VERSION,
            "mode": cfg["mode"], "is_demo": cfg["mode"] != "live", "policy_block": policy,
            "health": self.ctx.audit.health(self.ctx.data_source),
            "pulse_auto_refresh": cfg["pulse"]["auto_refresh_enabled"],
            "pulse_interval": cfg["pulse"]["refresh_interval_seconds"],
            "display_utc_offset": cfg["app"]["display_utc_offset"],
            "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    # ------------------------------------------------------------- modules
    def trace(self, body: dict) -> dict:
        return TraceabilityService(self.ctx).trace(validate_identifier(body.get("identifier")))

    def pulse(self, body: dict) -> dict:
        return PulseService(self.ctx).pulse(body)

    def quality(self, body: dict) -> dict:
        return QualityService(self.ctx).dashboard(body)

    def quality_close_times(self, body: dict) -> dict:
        ids = body.get("defect_ids")
        if not isinstance(ids, list) or len(ids) > 50:
            raise InputError("Lista de DefectID inválida")
        return QualityService(self.ctx).close_times(ids)

    def rework(self, body: dict) -> dict:
        if body.get("batch"):
            return ReworkService(self.ctx).by_batch(body["batch"])
        return ReworkService(self.ctx).by_identifier(validate_identifier(body.get("identifier")))

    def history(self, _body=None) -> dict:
        return {"searches": self.ctx.audit.searches(200), "queries": self.ctx.audit.recent_queries(100)}

    def history_clear(self, _body=None) -> dict:
        self.ctx.audit.clear_searches()
        return {"ok": True}

    def report(self, body: dict) -> tuple[bytes, str, str]:
        identifier = validate_identifier(body.get("identifier"))
        fmt = body.get("format", "csv")
        if fmt not in EXPORTERS:
            raise InputError("Formato de reporte no soportado")
        trace = self.ctx.audit.latest_analysis(self.ctx.data_source, "trace", identifier)
        if trace is None:
            trace = TraceabilityService(self.ctx).trace(identifier)
        func, ctype, ext = EXPORTERS[fmt]
        data = func(build_unit_report(trace))
        prefix = "DEMO_" if trace.get("is_demo") else ""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in identifier)
        return data, ctype, f"{prefix}GPV_Reporte_{safe}.{ext}"

    # ------------------------------------------------------------- config
    def get_config(self, _body=None) -> dict:
        out = public_config(self.ctx.config)
        out["credential_configured"] = credential_configured(self.ctx.config["odata"]) \
            if self.ctx.config["odata"]["auth_method"] == "basic" else None
        return out

    def save_config(self, body: dict) -> dict:
        values = body.get("values")
        if not isinstance(values, dict) or not values:
            raise InputError("No se recibieron valores")
        clean = {}
        for k, v in values.items():
            try:
                clean[k] = validate_setting(k, v)
            except ConfigError as exc:
                raise InputError(str(exc)) from exc
        self.ctx.settings.save(clean)
        self.ctx.reload()
        return self.get_config()

    def reset_config(self, _body=None) -> dict:
        self.ctx.settings.reset()
        self.ctx.reload()
        return self.get_config()

    # ------------------------------------------------------------- diagnostics
    def diagnostics(self, _body=None) -> dict:
        cfg = self.ctx.config
        url = urlsplit(cfg["odata"]["base_url"])
        policy = None
        if cfg["mode"] == "live":
            blocked = self.ctx.source.policy_check("*")
            policy = blocked.error if blocked else None
        return {
            "mode": cfg["mode"], "version": APP_VERSION,
            "base_url": cfg["odata"]["base_url"], "scheme": url.scheme, "host": url.hostname, "port": url.port,
            "auth_method": cfg["odata"]["auth_method"],
            "credential_source": cfg["odata"]["credential_source"],
            "credential_configured": credential_configured(cfg["odata"])
            if cfg["odata"]["auth_method"] == "basic" else None,
            "timeout_seconds": cfg["odata"]["timeout_seconds"],
            "max_retries": cfg["odata"]["max_retries"],
            "max_concurrent_requests": cfg["odata"]["max_concurrent_requests"],
            "policy_block": policy,
            "security": cfg["security"],
            "health": self.ctx.audit.health(self.ctx.data_source),
            "recent_queries": self.ctx.audit.recent_queries(30),
            "metadata_status": getattr(self.ctx.source, "last_metadata_status", None),
            "cache_counts": self.ctx.cache.counts(),
            "entities": list(KNOWN_ENTITIES),
            "python": sys.version.split()[0], "platform": platform.platform(),
        }

    def diagnostics_test(self, body: dict) -> dict:
        entity = body.get("entity")
        if entity == "$metadata":
            res, meta = self.ctx.source.fetch_metadata(force=True)
            if self.ctx.data_source == "demo":
                self.ctx.audit.record_query(res)
            out = {"result": res.to_status_dict()}
            if meta:
                out["odata_version"] = meta.odata_version
                out["entity_sets"] = sorted(meta.entity_sets)
                out["comparison"] = meta.compare_with_expected()
            return out
        if entity not in KNOWN_ENTITIES:
            raise InputError("Entidad no autorizada para diagnóstico")
        since = datetime.now(timezone.utc) - DIAG_WINDOWS[entity]
        res = self.ctx.execute(QuerySpec(entity, [Filter(DATE_FIELD[entity], "ge", since)], top=1))
        return {"result": res.to_status_dict(),
                "note": f"Consulta mínima: {DATE_FIELD[entity]} >= {since.isoformat(timespec='seconds')} con $top=1. "
                        "Un resultado EMPTY indica conectividad correcta sin registros en la ventana."}

    def diagnostics_text(self, _body=None) -> dict:
        d = self.diagnostics()
        lines = ["GPV SMT Quality Intelligence - Diagnóstico OData",
                 f"Timestamp: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
                 f"Versión: {d['version']}", f"Modo: {d['mode']}", f"Servidor: {d['host']}",
                 f"Puerto: {d['port']}", f"Esquema: {d['scheme']}",
                 f"Autenticación: {d['auth_method']} ({'configurada' if d['credential_configured'] else 'no configurada' if d['credential_configured'] is False else 'n/a'})",
                 f"Timeout: {d['timeout_seconds']} s | Reintentos: {d['max_retries']} | Concurrencia: {d['max_concurrent_requests']}",
                 f"Bloqueo de política: {d['policy_block'] or 'ninguno'}", "", "Salud por entidad:"]
        for h in d["health"]:
            lines.append(f"  {h['entity']}: {h['last_status']} HTTP={h['last_http']} "
                         f"{h['last_elapsed_ms']} ms | último OK={h['last_success_at']} | "
                         f"último error={h['last_error_at']} {h['last_error'] or ''} | fallos consecutivos={h['consecutive_failures']}")
        lines.append("")
        lines.append("Últimas consultas:")
        for q in d["recent_queries"][:10]:
            lines.append(f"  {q['ts']} {q['entity']} {q['status']} HTTP={q['http_status']} {q['elapsed_ms']} ms "
                         f"intentos={q['attempts']} filas={q['rows']} {q['error'] or ''}")
        lines.append(f"Python: {d['python']} | {d['platform']}")
        return {"text": "\n".join(lines)}

    def open_logs(self, _body=None) -> dict:
        path = resolve_path(self.ctx.config, "logs")
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - abre el Explorador local en la carpeta de logs
            return {"opened": True, "path": str(path)}
        return {"opened": False, "path": str(path)}
