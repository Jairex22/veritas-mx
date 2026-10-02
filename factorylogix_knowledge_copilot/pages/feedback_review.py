"""Bandeja de revisión de feedback y correcciones (aprobación humana obligatoria)."""
from __future__ import annotations

import streamlit as st

from models.domain import FL_MODULES, Classification
from ui.components import demo_banner, header, md
from ui.state import cid, container, guard, run_safely, tr


def render() -> None:
    user = guard("feedback.review")
    c = container()
    header(tr("nav.feedback"), "Las correcciones no se usan hasta que una persona las aprueba como Q&A.")
    demo_banner()
    queue = c.feedback.queue(user)
    st.metric("Correcciones pendientes", len(queue))
    for item in queue:
        with st.container(border=True):
            st.markdown(f"**Pregunta:** {md(item['question'] or '(sin consulta asociada)')}")
            st.markdown(f"**Comentario:** {md(item['comment'])}")
            with st.expander("Respuesta original"):
                st.text(item["original_answer"])
            with st.form(f"fb-{item['id']}"):
                question = st.text_input("Pregunta para la Q&A", value=item["question"][:500])
                answer = st.text_area("Respuesta corregida (debe basarse en un procedimiento vigente)",
                                      value=item["proposed_answer"])
                a, b = st.columns(2)
                module = a.selectbox("Módulo", FL_MODULES, index=FL_MODULES.index("General"))
                classification = b.selectbox("Clasificación", Classification.values(), index=1)
                note = st.text_input("Nota de revisión")
                x, y = st.columns(2)
                accept = x.form_submit_button("Convertir en Q&A propuesta", type="primary")
                dismiss = y.form_submit_button("Descartar")
            if accept:
                if run_safely(lambda: c.feedback.accept_correction(user, item["id"], question, answer, module,
                                                                   classification, note, cid()),
                              "Q&A propuesta creada. Debe aprobarla otra persona en Training Center."):
                    st.rerun()
            if dismiss:
                if run_safely(lambda: c.feedback.dismiss(user, item["id"], note, cid()) or True, "Descartada."):
                    st.rerun()
    st.markdown("### Todo el feedback")
    st.dataframe([{k: r[k] for k in ("created_at", "rating", "is_correction", "status", "question", "comment")}
                  for r in c.feedback.all_feedback(user)], hide_index=True)
