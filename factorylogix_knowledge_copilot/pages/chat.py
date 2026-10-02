"""Página de Chat."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from models.domain import FL_MODULES, SearchFilters
from sentiment.analyzer import PURPOSE_EN, PURPOSE_ES
from ui.components import demo_banner, header, md, render_answer
from ui.state import cid, container, guard, lang, run_safely, tr

SUGGESTED_ES = [
    "¿Cómo reviso el estado de una Work Order?", "¿Por qué una unidad no puede avanzar?",
    "¿Cómo sé cuál es la siguiente operación?", "¿Qué significa In Process?", "¿Dónde consulto la genealogía?",
    "¿Qué hago si el operador no está certificado?", "¿Qué diferencia existe entre Defect y Symptom?",
    "¿Por qué una unidad regresa a Repair?", "¿Cómo se documenta un reroute?",
    "¿Qué revisar si una etiqueta no coincide?", "¿Cómo consultar WIP?",
    "¿Qué información necesita MES para investigar un incidente?", "¿Cómo escalar un problema de FactoryLogix?",
]
SUGGESTED_EN = ["How do I check the status of a work order?", "What does a Fail result mean?",
                "What is serialization?", "Why can't a unit advance?"]


def _filter_values(catalog: list[dict], field: str) -> list[str]:
    return [""] + sorted({str(r.get(field) or "") for r in catalog if r.get(field)})


def _filters() -> SearchFilters:
    c = container()
    user = guard("chat.query")
    catalog = c.knowledge.catalog(user)
    with st.expander(tr("chat.filters")):
        cols = st.columns(6)
        values = {
            "customer": cols[0].selectbox("Cliente", _filter_values(catalog, "customer"), key="f_customer"),
            "product": cols[1].selectbox("Producto", _filter_values(catalog, "product"), key="f_product"),
            "line": cols[2].selectbox("Línea", _filter_values(catalog, "line"), key="f_line"),
            "process": cols[3].selectbox("Proceso", _filter_values(catalog, "process"), key="f_process"),
            "station": cols[4].selectbox("Estación", _filter_values(catalog, "station"), key="f_station"),
            "module": cols[5].selectbox("Módulo", [""] + FL_MODULES, key="f_module"),
        }
        st.caption("Los documentos genéricos (sin cliente/producto/línea) aplican a todos los filtros.")
    return SearchFilters(**values)


def _ask(question: str, filters: SearchFilters) -> None:
    c = container()
    user = guard("chat.query")
    with st.spinner("Buscando en conocimiento aprobado…"):
        answer = run_safely(lambda: c.chat.ask(user, question, filters, cid()))
    if answer is not None:
        st.session_state.setdefault("chat_history", []).append(answer)


def _live_query() -> None:
    c = container()
    user = guard("chat.query")
    if not user.can("connectors.query"):
        return
    status = c.connectors.status()["odata"]
    with st.expander(tr("ans.live") + " (solo lectura)"):
        if not (status["enabled"] and status["configured"]):
            st.info("Conector OData desactivado (feature flag). La aplicación funciona solo con documentos aprobados.")
            return
        entities = c.connectors.entities
        entity = st.selectbox("Entidad", sorted(entities))
        key_field = st.selectbox("Buscar por", entities[entity].get("key_fields", []))
        value = st.text_input("Valor (WO, serial, usuario…)", max_chars=64)
        if st.button("Consultar FactoryLogix"):
            result = run_safely(lambda: c.connectors.query(user, entity, key_field, value, cid()))
            if result is not None:
                st.caption(f"{result.source_label} · {result.retrieved_at}" + (" · caché" if result.from_cache else ""))
                st.dataframe(pd.DataFrame(result.rows), hide_index=True)
                st.caption("Estos datos provienen de FactoryLogix en vivo; no son información documental ni "
                           "una inferencia del sistema. El asistente no modifica datos de producción.")


def render() -> None:
    user = guard("chat.query")
    c = container()
    header(tr("chat.title"), tr("chat.subtitle"))
    demo_banner()
    history = st.session_state.get("chat_history", [])

    with st.form("ask", clear_on_submit=True):
        question = st.text_area(tr("chat.question"), height=110,
                                max_chars=int(c.settings.get("security.max_question_chars", 1500)),
                                placeholder="Ej.: ¿Por qué una unidad no puede avanzar en la estación de prueba?")
        submitted = st.form_submit_button(tr("chat.ask"), type="primary")
    filters = _filters()
    suggestions = SUGGESTED_EN if lang() == "en" else SUGGESTED_ES
    with st.expander(tr("chat.suggested"), expanded=not history):
        cols = st.columns(3)
        for i, suggestion in enumerate(suggestions):
            if cols[i % 3].button(suggestion, key=f"sug-{i}"):
                _ask(suggestion, filters)
                st.rerun()
    if submitted and question.strip():
        _ask(question, filters)
        st.rerun()

    _live_query()
    if c.settings.get("sentiment.enabled", True):
        st.caption("ℹ️ " + (PURPOSE_EN if lang() == "en" else PURPOSE_ES))

    if history:
        top_l, top_r = st.columns([4, 1])
        top_l.markdown(f"### {tr('chat.history')}")
        if top_r.button(tr("chat.clear")):
            st.session_state["chat_history"] = []
            st.rerun()
    for idx in range(len(history) - 1, -1, -1):
        answer = history[idx]
        with st.container(border=True):
            st.markdown(f"**🧑‍🏭 {md(answer.question[:400])}**")
            render_answer(answer, user, f"{idx}-{answer.query_id}", lang())
