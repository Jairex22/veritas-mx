"""Módulo D - Rework & Loop Detector."""
from __future__ import annotations

from datetime import datetime, timezone

from analytics.rework_rules import RULES, evaluate
from backend.security import validate_term
from models.query import Filter, QuerySpec
from services.traceability_service import TraceabilityService


class ReworkService:
    def __init__(self, ctx):
        self.ctx = ctx

    def by_identifier(self, identifier: str) -> dict:
        trace = TraceabilityService(self.ctx).trace(identifier)
        return {"mode": "identifier", "data_source": trace["data_source"], "is_demo": trace["is_demo"],
                "identifier": identifier, "sources": trace["sources"], "alerts": trace["alerts"],
                "rules": RULES_PUBLIC, "units": [{"identifier": identifier, "events": trace["summary"]["smt_events"],
                                                   "alerts": trace["alerts"]}]}

    def by_batch(self, batch: str) -> dict:
        batch = validate_term(batch, "Batch", required=True)
        cfg, ds = self.ctx.config, self.ctx.data_source
        res = self.ctx.execute(QuerySpec("SMT", [Filter("Batch", "eq", batch)], orderby=[("EventDate", "asc")],
                                         top=int(cfg["rework"]["max_batch_events"])))
        if res.ok:
            self.ctx.cache.store("SMT", res.rows, ds)
        groups: dict[str, list[dict]] = {}
        for r in res.rows:
            groups.setdefault(r.get("Identifier") or "(sin Identifier)", []).append(r)
        units = []
        for ident, rows in sorted(groups.items()):
            alerts = evaluate(ident, rows, [], cfg["rework"]["repair_keywords"], cfg["rework"]["process_flows"])
            if alerts:
                units.append({"identifier": ident, "events": len(rows), "alerts": alerts})
        self.ctx.audit.add_search(ds, "rework", batch, f"{len(units)} unidades con alertas")
        return {"mode": "batch", "data_source": ds, "is_demo": ds == "demo", "batch": batch,
                "source": res.to_status_dict(), "units_observed": len(groups), "units": units, "rules": RULES_PUBLIC,
                "notes": ["Análisis por batch usa solo la entidad SMT; los defectos se consultan en la vista por unidad."]
                + (["Resultado truncado al límite configurado de eventos."] if res.truncated else []),
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


RULES_PUBLIC = [{"rule": k, "category": v[0], "title": v[1], "definition": v[2]} for k, v in RULES.items()]
