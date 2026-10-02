"""Analítica responsable (agregada; sin rankings ni métricas por empleado)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.analytics_service import ANALYTICS_NOTICE
from services.export_service import to_csv_bytes
from ui.components import demo_banner, header
from ui.state import container, guard, tr


def render() -> None:
    user = guard("analytics.view")
    c = container()
    header(tr("nav.analytics"), "Uso, cobertura y salud del conocimiento.")
    demo_banner()
    st.info(ANALYTICS_NOTICE)
    data = c.analytics.summary(user)
    cols = st.columns(5)
    cols[0].metric("Preguntas", data["total_questions"])
    cols[1].metric("Sin respuesta", data["unanswered"])
    cols[2].metric("Cobertura", f"{data['coverage']:.0%}")
    cols[3].metric("Latencia prom. / p95", f"{data['avg_latency_ms']} / {data['p95_latency_ms']} ms")
    cols[4].metric("Conflictos detectados", data["conflicts"])
    cols = st.columns(5)
    cols[0].metric("Feedback 👍", data["feedback_up"])
    cols[1].metric("Feedback 👎", data["feedback_down"])
    cols[2].metric("Fuentes vencidas / críticas", len(data["expired_or_overdue"]))
    cols[3].metric("Errores del sistema", data["system_errors"])
    cols[4].metric("Docs publicados", data["index"]["published_documents"])
    if data["per_day"]:
        st.markdown("**Preguntas por día**")
        st.bar_chart(pd.DataFrame(data["per_day"]).set_index("fecha"))
    left, right = st.columns(2)
    with left:
        st.markdown("**Temas más consultados**")
        st.dataframe(data["top_topics"], hide_index=True)
        st.markdown("**Documentos más utilizados (fuente principal)**")
        st.dataframe(data["top_documents"], hide_index=True)
    with right:
        st.markdown("**Preguntas candidatas para nuevo contenido (sin respuesta)**")
        st.dataframe(data["candidate_questions"], hide_index=True)
        if data["candidate_questions"] and user.can("export.data"):
            st.download_button("Exportar candidatas (CSV)", data=to_csv_bytes(data["candidate_questions"]),
                               file_name="preguntas_candidatas.csv")
    st.markdown("**Fuentes vencidas o con hallazgos críticos**")
    st.dataframe(data["expired_or_overdue"], hide_index=True)
    st.markdown("**Salud del índice**")
    st.json(data["index"])
    st.caption(f"Idioma: {data['by_language']} · Modo: {data['by_mode']} · Confianza: {data['confidence_levels']}")
