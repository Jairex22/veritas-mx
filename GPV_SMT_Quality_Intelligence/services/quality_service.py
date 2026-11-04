"""Módulo C - Quality Intelligence (defectos únicos por DefectID)."""
from __future__ import annotations

from datetime import datetime, timezone

from analytics.defects import group_defects, summarize_defects
from backend.security import validate_guid, validate_term
from models.query import Filter, QuerySpec
from models.results import ODataStatus
from services.odata_filters import MAX_IN_VALUES
from services.timeparse import parse_offset
from services.windows import resolve_window

FILTER_MAP = {"assembly": "Assembly", "batch": "BatchName", "status": "DefectStatus", "line": "Line",
              "customer": "CustomerName", "operation": "SourceOperation"}


class QualityService:
    def __init__(self, ctx):
        self.ctx = ctx

    def dashboard(self, params: dict) -> dict:
        cfg, ds = self.ctx.config, self.ctx.data_source
        if params.get("window") is None:
            params = dict(params, window="24h")
        start, end, label = resolve_window(params, cfg)
        filters = [Filter("DateCreated", "ge", start), Filter("DateCreated", "le", end)]
        applied = {}
        for key, field in FILTER_MAP.items():
            val = validate_term(params.get(key), key)
            if val:
                filters.append(Filter(field, "eq", val))
                applied[key] = val
        res = self.ctx.execute(QuerySpec("Quality", filters, orderby=[("DateCreated", "desc")],
                                         top=int(cfg["quality"]["max_defects"])))
        rows = res.rows
        if res.ok:
            self.ctx.cache.store("Quality", rows, ds)
        else:
            cached, cached_at = self.ctx.cache.quality_in_window(start, end, ds, int(cfg["quality"]["max_defects"]))
            rows = [r for r in cached if all(r.get(FILTER_MAP[k]) == v for k, v in applied.items())]
            if rows:
                res.stale, res.cached_at = True, cached_at
        # En el dashboard no se consulta QualityHistory automáticamente (carga).
        defects = group_defects(rows, [], history_available=True)
        for d in defects:
            if d["classification"] == "HISTORY_INCOMPLETE":
                d["classification"] = "CLOSED"
            d["notes"] = [n for n in d["notes"] if "sin registro histórico" not in n]
            d["notes"].append("Historial no consultado en el dashboard (use 'Calcular tiempos de cierre')")
        summary = summarize_defects(defects)
        result = {
            "data_source": ds, "is_demo": ds == "demo",
            "window": {"label": label,
                       "start": start.astimezone(parse_offset(cfg["app"]["display_utc_offset"])).isoformat(timespec="seconds"),
                       "end": end.astimezone(parse_offset(cfg["app"]["display_utc_offset"])).isoformat(timespec="seconds")},
            "filters": applied, "source": res.to_status_dict(),
            "summary": summary,
            "defects": [{k: v for k, v in d.items() if k != "history"} for d in defects],
            "notes": [
                "Los defectos se cuentan por DefectID único.",
                "Un defecto Closed no significa que la unidad esté aprobada.",
                "BatchQuantity y CompletedQuantity no se usan como unidades aprobadas.",
            ] + (["Resultado truncado al límite configurado."] if res.truncated else []),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.ctx.audit.add_search(ds, "quality", label, f"{summary['unique_defects']} defectos únicos")
        return result

    def close_times(self, defect_ids: list) -> dict:
        cfg, ds = self.ctx.config, self.ctx.data_source
        limit = int(cfg["quality"]["max_closetime_lookups"])
        ids = sorted({validate_guid(d) for d in (defect_ids or [])}, key=str.lower)[:limit]
        if not ids:
            return {"source": None, "defects": [], "data_source": ds}
        rows, last = [], None
        for i in range(0, len(ids), MAX_IN_VALUES):
            res = self.ctx.execute(QuerySpec("QualityHistory", [Filter("DefectID", "in", ids[i:i + MAX_IN_VALUES])],
                                             orderby=[("DefectHistoryTime", "asc")], top=500))
            last = res
            if not res.ok:
                break
            rows.extend(res.rows)
            self.ctx.cache.store("QualityHistory", res.rows, ds)
        quality_rows = []
        for d in ids:
            q, _ = self.ctx.cache.quality_by_defect(d, ds)
            quality_rows.extend(q[:1] or [{"DefectID": d}])
        ok = last is not None and last.status in (ODataStatus.OK, ODataStatus.EMPTY)
        defects = group_defects(quality_rows, rows, history_available=ok)
        return {"data_source": ds, "source": last.to_status_dict() if last else None,
                "defects": [{k: v for k, v in d.items() if k != "history"} for d in defects],
                "limited_to": limit}
