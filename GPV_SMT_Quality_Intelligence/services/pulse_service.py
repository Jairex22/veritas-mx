"""Módulo B - SMT Production Pulse.

Indicadores basados en eventos de la entidad SMT. No calcula PASS/FAIL ni
tarjetas buenas: los identificadores únicos solo indican unidades observadas.
"""
from __future__ import annotations

from datetime import datetime, timezone

from analytics.rework_rules import is_repair
from backend.security import validate_term
from models.query import Filter, QuerySpec
from services.timeparse import parse_odata_datetime, parse_offset, sort_key
from services.windows import resolve_window

FILTER_MAP = {"customer": "Customer", "assembly": "Assembly", "batch": "Batch", "operation": "OperationName"}


def _count(rows: list[dict], field: str) -> list[dict]:
    acc: dict[str, int] = {}
    for r in rows:
        k = r.get(field) or "(vacío)"
        acc[k] = acc.get(k, 0) + 1
    return [{"key": k, "count": v} for k, v in sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))]


class PulseService:
    def __init__(self, ctx):
        self.ctx = ctx

    def pulse(self, params: dict) -> dict:
        cfg, ds = self.ctx.config, self.ctx.data_source
        start, end, label = resolve_window(params, cfg)
        filters = [Filter("EventDate", "ge", start), Filter("EventDate", "le", end)]
        applied = {}
        for key, field in FILTER_MAP.items():
            val = validate_term(params.get(key), key)
            if val:
                filters.append(Filter(field, "eq", val))
                applied[key] = val
        max_events = int(cfg["pulse"]["max_events"])
        res = self.ctx.execute(QuerySpec("SMT", filters, orderby=[("EventDate", "desc")], top=max_events))
        if res.ok:
            self.ctx.cache.store("SMT", res.rows, ds)
            rows = res.rows
        else:
            cached, cached_at = self.ctx.cache.smt_in_window(start, end, ds, max_events)
            rows = [r for r in cached if all(r.get(FILTER_MAP[k]) == v for k, v in applied.items())]
            if rows:
                res.stale, res.cached_at = True, cached_at
        keywords = cfg["rework"]["repair_keywords"]
        ident_ops: dict[tuple, int] = {}
        for r in rows:
            k = (r.get("Identifier"), r.get("OperationName"))
            ident_ops[k] = ident_ops.get(k, 0) + 1
        repeated_idents = sorted({i for (i, _), n in ident_ops.items() if n > 1 and i})
        dated = [r for r in rows if sort_key(parse_odata_datetime(r.get("EventDate")))[0] == 0]
        last = max(dated, key=lambda r: parse_odata_datetime(r.get("EventDate")), default=None)
        kpis = {
            "events": len(rows),
            "unique_identifiers": len({r.get("Identifier") for r in rows if r.get("Identifier")}),
            "assemblies": len({r.get("Assembly") for r in rows if r.get("Assembly")}),
            "batches": len({r.get("Batch") for r in rows if r.get("Batch")}),
            "operations": len({r.get("OperationName") for r in rows if r.get("OperationName")}),
            "last_event": last.get("EventDate") if last else None,
            "repeated_identifiers": len(repeated_idents),
            "repair_events": sum(1 for r in rows if is_repair(r.get("OperationName"), keywords)),
            "response_ms": round(res.elapsed_ms, 1),
        }
        result = {
            "data_source": ds, "is_demo": ds == "demo",
            "window": {"label": label,
                       "start": start.astimezone(parse_offset(cfg["app"]["display_utc_offset"])).isoformat(timespec="seconds"),
                       "end": end.astimezone(parse_offset(cfg["app"]["display_utc_offset"])).isoformat(timespec="seconds")},
            "filters": applied,
            "source": res.to_status_dict(),
            "kpis": kpis,
            "by_customer": _count(rows, "Customer"),
            "by_assembly": _count(rows, "Assembly"),
            "by_batch": _count(rows, "Batch"),
            "by_operation": _count(rows, "OperationName"),
            "repeated_identifiers": repeated_idents[:100],
            "events": rows[:max_events],
            "line_filter": {"available": False,
                            "reason": "La entidad SMT no expone Line; no existe relación comprobable."},
            "notes": [
                "Los eventos no equivalen a tarjetas producidas ni a unidades aprobadas.",
                "Attempts y Placements no se interpretan como tarjetas producidas.",
                "La entidad SMT puede incluir operaciones de otras áreas (p. ej. FCT).",
            ] + (["Resultado truncado al límite configurado de eventos."] if res.truncated else []),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.ctx.audit.add_search(ds, "pulse", label, f"{kpis['events']} eventos")
        return result
