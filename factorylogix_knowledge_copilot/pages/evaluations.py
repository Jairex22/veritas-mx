"""Evaluación del RAG: métricas de calidad, seguridad y resiliencia."""
from __future__ import annotations

import streamlit as st

from services.export_service import to_csv_bytes
from ui.components import demo_banner, header
from ui.state import cid, container, guard, run_safely, tr

METRIC_LABELS = {
    "retrieval_hit_rate": "Recuperación de fuente correcta", "citation_precision": "Precisión de cita principal",
    "faithfulness_avg": "Fidelidad", "relevance_avg": "Relevancia", "coverage": "Cobertura",
    "no_evidence_accuracy": "Detección sin evidencia", "hallucination_rate": "Tasa de alucinación",
    "conflict_detection": "Detección de conflictos", "access_control_leaks": "Fugas de control de acceso",
    "latency_p50_ms": "Latencia p50 (ms)", "latency_p95_ms": "Latencia p95 (ms)",
    "resilience_passed": "Resiliencia", "cases_passed": "Casos aprobados", "cases": "Casos",
}


def _show(result: dict) -> None:
    summary = result["summary"]
    keys = [k for k in METRIC_LABELS if k in summary]
    for i in range(0, len(keys), 4):
        cols = st.columns(4)
        for col, key in zip(cols, keys[i:i + 4]):
            value = summary[key]
            col.metric(METRIC_LABELS[key], "—" if value is None else value)
    st.markdown("**Casos**")
    st.dataframe(result["details"], hide_index=True)
    st.markdown("**Resiliencia del sistema**")
    st.dataframe(result["resilience"], hide_index=True)
    st.download_button("Descargar resultados (CSV)", data=to_csv_bytes(result["details"]),
                       file_name="evaluacion_rag.csv")


def render() -> None:
    user = guard("eval.view")
    c = container()
    header(tr("nav.evaluations"), "Preguntas de referencia: evidencia, sin evidencia, vencidos, conflictos, "
                                  "restringidos, prompt injection, idiomas y resiliencia.")
    demo_banner()
    st.caption("La fidelidad del modo extractivo es alta por construcción (solo copia texto de fuentes); la "
               "métrica es relevante cuando se activa un LLM local.")
    if user.can("eval.run") and st.button("Ejecutar evaluación", type="primary"):
        with st.spinner("Evaluando…"):
            result = run_safely(lambda: c.evaluation.run(user, cid()))
        if result:
            st.session_state["eval_result"] = result
            paths = run_safely(lambda: c.evaluation.export(result, c.settings.path("paths.reports_dir")))
            if paths:
                st.caption(f"Reportes guardados en reports/: {paths[0].name}, {paths[1].name}")
    if "eval_result" in st.session_state:
        _show(st.session_state["eval_result"])
    st.markdown("### Historial")
    history = c.evaluation.history(user)
    st.dataframe([{"Fecha": h["finished_at"], "Usuario": h["run_by"],
                   "Aprobados": f"{h['summary'].get('cases_passed')}/{h['summary'].get('cases')}",
                   "Recuperación": h["summary"].get("retrieval_hit_rate"),
                   "Alucinación": h["summary"].get("hallucination_rate"),
                   "Fugas acceso": h["summary"].get("access_control_leaks")} for h in history], hide_index=True)
