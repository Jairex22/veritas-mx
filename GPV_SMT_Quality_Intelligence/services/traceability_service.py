"""Módulo A - Trazabilidad de unidad (SMT + Quality + QualityHistory)."""
from __future__ import annotations

from datetime import datetime, timezone

from analytics.defects import group_defects
from analytics.evidence import CLOSURE_DISCLAIMER, classify
from analytics.rework_rules import evaluate
from analytics.timeline import build_timeline
from models.query import Filter, QuerySpec
from models.results import ODataStatus, QueryResult
from services.odata_filters import MAX_IN_VALUES


def _with_cache_fallback(result: QueryResult, cached: tuple[list[dict], str | None]) -> QueryResult:
    """Ante error, usa la última lectura válida de la caché marcándola como desactualizada."""
    rows, cached_at = cached
    if result.ok or not rows:
        return result
    result.rows = rows
    result.stale = True
    result.cached_at = cached_at
    return result


class TraceabilityService:
    def __init__(self, ctx):
        self.ctx = ctx

    def trace(self, identifier: str) -> dict:
        cfg, ds = self.ctx.config, self.ctx.data_source
        tcfg = cfg["trace"]
        smt = self.ctx.execute(QuerySpec("SMT", [Filter("Identifier", "eq", identifier)],
                                         orderby=[("EventDate", "asc")], top=tcfg["max_smt_events"]))
        if smt.ok:
            self.ctx.cache.store("SMT", smt.rows, ds)
        else:
            smt = _with_cache_fallback(smt, self.ctx.cache.smt_by_identifier(identifier, ds))

        quality = self.ctx.execute(QuerySpec("Quality", [Filter("Identifier", "eq", identifier)],
                                             top=tcfg["max_quality_rows"]))
        if quality.ok:
            self.ctx.cache.store("Quality", quality.rows, ds)
        else:
            quality = _with_cache_fallback(quality, self.ctx.cache.quality_by_identifier(identifier, ds))

        defect_ids = sorted({r["DefectID"] for r in quality.rows if r.get("DefectID")}, key=str.lower)
        history = self._history(defect_ids, tcfg["max_history_rows"])

        sources = {"SMT": smt.to_status_dict(), "Quality": quality.to_status_dict(),
                   "QualityHistory": history.to_status_dict()}
        history_available = history.ok or (history.stale and bool(history.rows))
        defects = group_defects(quality.rows, history.rows, history_available or not defect_ids)
        alerts = evaluate(identifier, smt.rows, defects, cfg["rework"]["repair_keywords"],
                          cfg["rework"]["process_flows"])
        evidence = classify(identifier, smt.rows, defects, alerts, sources, cfg["rework"]["repair_keywords"])
        timeline = build_timeline(smt.rows, quality.rows, history.rows)

        header = self._header(identifier, smt.rows, quality.rows)
        ops_count: dict[str, int] = {}
        for r in smt.rows:
            ops_count[r.get("OperationName") or "(sin nombre)"] = ops_count.get(r.get("OperationName") or "(sin nombre)", 0) + 1

        all_failed = not any(s["ok"] or s["stale"] for k, s in sources.items() if s["status"] != "NOT_REQUESTED")
        found = bool(smt.rows or quality.rows)
        result = {
            "identifier": identifier,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data_source": ds,
            "is_demo": ds == "demo",
            "state": "ERROR" if all_failed else ("FOUND" if found else "NOT_FOUND"),
            "header": header,
            "sources": sources,
            "summary": {
                "smt_events": len(smt.rows),
                "operations": [{"operation": k, "count": v} for k, v in ops_count.items()],
                "unique_defects": len(defects),
                "history_entries": len(history.rows),
                "repeated_operations": [k for k, v in ops_count.items() if v > 1],
                "final_result": evidence["final_result"],
            },
            "timeline": timeline,
            "defects": defects,
            "alerts": alerts,
            "evidence": evidence,
            "disclaimer": CLOSURE_DISCLAIMER,
            "smt_events": smt.rows,
        }
        summary_txt = f"{len(smt.rows)} eventos, {len(defects)} defectos, estado {result['state']}"
        self.ctx.audit.add_search(ds, "trace", identifier, summary_txt)
        self.ctx.audit.save_analysis(ds, "trace", identifier, result)
        return result

    def _history(self, defect_ids: list[str], top: int) -> QueryResult:
        ds = self.ctx.data_source
        if not defect_ids:
            return QueryResult(ODataStatus.NOT_REQUESTED, "QualityHistory", data_source=ds,
                               query_description="Sin DefectID asociados: no se consulta QualityHistory")
        merged: QueryResult | None = None
        for i in range(0, len(defect_ids), MAX_IN_VALUES):
            chunk = defect_ids[i:i + MAX_IN_VALUES]
            res = self.ctx.execute(QuerySpec("QualityHistory", [Filter("DefectID", "in", chunk)],
                                             orderby=[("DefectHistoryTime", "asc")], top=top))
            if merged is None:
                merged = res
            else:
                merged.elapsed_ms += res.elapsed_ms
                merged.attempts += res.attempts
                if res.ok:
                    merged.rows.extend(res.rows)
                if not res.ok:
                    merged.status, merged.error, merged.http_status = res.status, res.error, res.http_status
            if not res.ok:
                break
        assert merged is not None
        if merged.ok:
            merged.status = ODataStatus.OK if merged.rows else ODataStatus.EMPTY
            self.ctx.cache.store("QualityHistory", merged.rows, ds)
        else:
            merged.rows = []
            merged = _with_cache_fallback(merged, self.ctx.cache.history_by_defects(defect_ids, ds))
        return merged

    @staticmethod
    def _header(identifier: str, smt_rows: list[dict], quality_rows: list[dict]) -> dict:
        def first(rows, *keys):
            for r in rows:
                for k in keys:
                    if r.get(k):
                        return r[k]
            return None
        lines = sorted({r["Line"] for r in quality_rows if r.get("Line")})
        return {
            "identifier": identifier,
            "customer": first(smt_rows, "Customer") or first(quality_rows, "CustomerName"),
            "assembly": first(smt_rows, "Assembly") or first(quality_rows, "Assembly"),
            "assembly_revision": first(smt_rows, "AssemblyRevision") or first(quality_rows, "AssemblyRevision"),
            "batch": first(smt_rows, "Batch") or first(quality_rows, "BatchName"),
            "work_order": first(smt_rows, "WorkOrder") or first(quality_rows, "WorkOrder"),
            "lot": first(quality_rows, "Lot"),
            "lines_registered_in_defects": lines,
            "line_verified": False,
            "line_note": ("Línea registrada únicamente en defectos de Quality; no verificada para todas las "
                          "operaciones." if lines else "No verificable: la entidad SMT no expone la línea."),
        }
