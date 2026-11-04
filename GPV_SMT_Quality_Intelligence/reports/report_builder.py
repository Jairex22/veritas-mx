"""Construcción de reportes de unidad a partir del análisis de trazabilidad.

El reporte se arma como secciones tabulares neutrales al formato; los
exportadores CSV/XLSX/HTML solo cambian la representación.
"""
from __future__ import annotations

from datetime import datetime, timezone

from analytics.evidence import CLOSURE_DISCLAIMER
from backend.config import APP_VERSION

FINAL_LABEL = {"NO_VERIFICABLE": "NO VERIFICABLE (no existe evidencia de aprobación final)"}


def build_unit_report(trace: dict) -> dict:
    h = trace["header"]
    demo = trace.get("is_demo")
    general = [
        ["Reporte", "GPV SMT Quality Intelligence - Reporte de unidad"],
        ["Fecha de generación", datetime.now(timezone.utc).isoformat(timespec="seconds")],
        ["Análisis realizado", trace.get("generated_at")],
        ["Versión", APP_VERSION],
        ["Fuente de datos", "DEMOSTRACIÓN (no producción)" if demo else "FactoryLogix OData"],
        ["Cliente", h.get("customer") or "No verificable"],
        ["Assembly", h.get("assembly") or "No verificable"],
        ["Revisión", h.get("assembly_revision") or "No verificable"],
        ["Batch", h.get("batch") or "No verificable"],
        ["Lot", h.get("lot") or "No verificable"],
        ["Identifier", trace["identifier"]],
        ["Línea", ", ".join(h.get("lines_registered_in_defects") or []) or "No verificable"],
        ["Nota de línea", h.get("line_note")],
        ["Resultado final", FINAL_LABEL.get(trace["summary"]["final_result"], trace["summary"]["final_result"])],
    ]
    sources = [["Fuente", "Estado", "HTTP", "Tiempo (ms)", "Registros", "Desactualizado", "Error"]] + [
        [k, v["status"], v.get("http_status") or "", v.get("elapsed_ms"), v.get("rows"),
         "Sí" if v.get("stale") else "No", v.get("error") or ""] for k, v in trace["sources"].items()]
    events = [["Fecha", "Operación", "Batch", "Assembly", "WorkOrder"]] + [
        [r.get("EventDate"), r.get("OperationName"), r.get("Batch"), r.get("Assembly"), r.get("WorkOrder")]
        for r in trace.get("smt_events", [])]
    defects = [["DefectID", "Descripción", "Comentario", "Referencia", "Estado", "Clasificación", "Operación origen",
                "Estación inspección", "Línea registrada", "Creado", "Cerrado", "Min. a cierre", "Notas"]] + [
        [d["defect_id"], d.get("description"), d.get("comment"), d.get("reference"), d.get("status"),
         d.get("classification"), d.get("source_operation"), d.get("inspection_workstation"),
         d.get("line_registered"), d.get("date_created"), d.get("closed_at"), d.get("time_to_close_min"),
         "; ".join(d.get("notes", []))] for d in trace["defects"]]
    history = [["DefectID", "Hora", "Estado histórico", "Operación", "Estación", "Operador", "Comentario"]]
    for d in trace["defects"]:
        for e in d.get("history", []):
            history.append([e.get("DefectID"), e.get("DefectHistoryTime"), e.get("DefectHistoryStatus"),
                            e.get("DefectHistoryOperation"), e.get("DefectHistoryWorkstation"),
                            e.get("DefectHistoryOperator"), e.get("DefectHistoryComment")])
    rework = [["Regla", "Categoría", "Confianza", "Explicación", "Evidencia", "No se puede concluir"]] + [
        [a["rule"], a["title"], a["confidence"], a["explanation"], ", ".join(a["evidence"]),
         "; ".join(a["cannot_conclude"])] for a in trace["alerts"]]
    ev = trace["evidence"]
    evidence = [["Tipo", "Descripción"]] + [["Evidencia confirmada", x] for x in ev["confirmed"]] + \
               [["Hipótesis / inferencia", x] for x in ev["inferred"]] + \
               [["Pendiente de verificar", x] for x in ev["unverifiable"]]
    return {
        "title": f"Reporte de unidad {trace['identifier']}",
        "identifier": trace["identifier"],
        "is_demo": demo,
        "disclaimer": CLOSURE_DISCLAIMER,
        "sections": [
            ("General", general),
            ("Fuentes OData", sources),
            ("Eventos de proceso", events),
            ("Defectos", defects),
            ("Historial de calidad", history),
            ("Posibles reprocesos", rework),
            ("Evidencia", evidence),
        ],
    }
