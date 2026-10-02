"""Componentes de interfaz reutilizables: tarjeta de respuesta, confianza, fuentes y acciones."""
from __future__ import annotations

import streamlit as st

from models.domain import Answer, AuthenticatedUser, Urgency
from schemas.validation import IncidentInput
from security.rbac import DETAIL_LEVEL
from security.sanitize import escape_html, escape_markdown
from sentiment.analyzer import tone_guidance
from ui.state import cid, container, run_safely, tr

_LEVEL_CSS = {"High": "flkc-high", "Medium": "flkc-medium", "Low": "flkc-low", "None": "flkc-none"}
_LEVEL_TXT = {"es": {"High": "Alta", "Medium": "Media", "Low": "Baja", "None": "Sin evidencia"},
              "en": {"High": "High", "Medium": "Medium", "Low": "Low", "None": "No evidence"}}


def md(text: str) -> str:
    return escape_markdown(text or "")


def header(title: str, subtitle: str = "") -> None:
    st.markdown(f"<div class='flkc-header'><div class='t'>{escape_html(title)}</div>"
                f"<div class='s'>{escape_html(subtitle)}</div></div>", unsafe_allow_html=True)


def demo_banner() -> None:
    env = str(container().settings.get("app.environment", "DEMO")).upper()
    if env != "PRODUCTION":
        st.markdown(f"<div class='flkc-banner'>{escape_html(env)} · {escape_html(tr('common.demo_banner'))}</div>",
                    unsafe_allow_html=True)


def confidence_badge(answer: Answer, lang: str) -> None:
    conf = answer.confidence
    level = conf.level if conf else "None"
    pct = f" · {conf.score:.0%}" if conf and conf.score else ""
    label = _LEVEL_TXT.get(lang, _LEVEL_TXT["es"]).get(level, level)
    st.markdown(f"<span class='flkc-badge {_LEVEL_CSS.get(level, 'flkc-none')}' role='status' "
                f"aria-label='{escape_html(tr('ans.confidence'))}'>{escape_html(tr('ans.confidence'))}: "
                f"{escape_html(label)}{escape_html(pct)}</span>", unsafe_allow_html=True)


def _section(title: str, items: list[str], numbered: bool = False, short: bool = False,
             show_empty: bool = True) -> None:
    if not items and not show_empty:
        return
    st.markdown(f"<div class='flkc-section'>{escape_html(title)}</div>", unsafe_allow_html=True)
    if not items:
        st.caption(tr("ans.not_specified"))
        return
    lines = []
    for i, item in enumerate(items, start=1):
        text = item if not short or len(item) < 160 else item[:157] + "…"
        lines.append(f"{i}. {md(text)}" if numbered else f"- {md(text)}")
    st.markdown("\n".join(lines))


def _evidence_text(answer: Answer) -> str:
    parts = [answer.as_text(), "", "=== EVIDENCIA ==="]
    for s in answer.sources:
        page = f" pág. {s.page}" if s.page else ""
        parts += [f"[{s.doc_code} v{s.version_label}] {s.title} · {s.section}{page} · {s.classification}",
                  s.excerpt, ""]
    parts.append(f"Correlation ID: {answer.correlation_id}")
    return "\n".join(parts)


def render_answer(answer: Answer, user: AuthenticatedUser, key: str, lang: str) -> None:
    detail = DETAIL_LEVEL.get(user.role, "operator")
    tone = tone_guidance(answer.sentiment.label, answer.language) if answer.sentiment else tone_guidance("", lang)

    confidence_badge(answer, lang)
    if answer.safety_stop:
        for w in answer.warnings[:1]:
            st.error(w)
    for notice in answer.notices:
        st.warning(notice)
    if answer.conflicts:
        st.error(tr("ans.conflict"))
        for c in answer.conflicts:
            st.markdown(f"- **{md(c.doc_a)}**: {md(c.sentence_a)}\n- **{md(c.doc_b)}**: {md(c.sentence_b)}")
    if tone.get("preface"):
        st.info(str(tone["preface"]))

    if not answer.answered:
        st.markdown(md(answer.brief))
        st.markdown(f"**{tr('ans.route')}:** {md(answer.escalation_route)}")
        _actions(answer, user, key)
        return

    if tone.get("escalation_first"):
        _section(tr("ans.escalate"), answer.escalate_when)
        st.markdown(f"**{tr('ans.route')}:** {md(answer.escalation_route)}")

    st.markdown(f"<div class='flkc-section'>{escape_html(tr('ans.doc_info'))} · {escape_html(tr('ans.brief'))}</div>",
                unsafe_allow_html=True)
    st.markdown(md(answer.brief))

    brief_only = bool(tone.get("brief_only"))
    container_ = st.expander(tr("ans.steps") + " …", expanded=False) if brief_only else st.container()
    with container_:
        _section(tr("ans.steps"), answer.steps, numbered=True, short=bool(tone.get("short_steps")))
        _section(tr("ans.validate"), answer.validate)
        _section(tr("ans.expected"), answer.expected)
        _section(tr("ans.stop"), answer.stop_when)
        if not tone.get("escalation_first"):
            _section(tr("ans.escalate"), answer.escalate_when)
            st.markdown(f"**{tr('ans.route')}:** {md(answer.escalation_route)}")
        warnings = answer.warnings[1:] if answer.safety_stop else answer.warnings
        _section(tr("ans.warnings"), warnings, show_empty=False)

    if answer.system_inference:
        st.markdown(f"<div class='flkc-section'>{escape_html(tr('ans.inference'))}</div>", unsafe_allow_html=True)
        st.markdown("\n".join(f"- {md(i)}" for i in answer.system_inference))

    with st.expander(f"{tr('ans.sources')} ({len(answer.sources)})", expanded=detail != "operator"):
        for i, s in enumerate(answer.sources):
            page = f" · pág. {s.page}" if s.page else ""
            demo = " · DEMO" if s.is_demo else ""
            st.markdown(f"**{md(s.doc_code)}** · {md(s.title)} · v{md(s.version_label)} · {md(s.source_type)} · "
                        f"{md(s.classification)}{demo}")
            st.caption(f"{s.section}{page} · revisión: {s.review_date or '—'} · expira: {s.expiration_date or '—'}"
                       + (f" · relevancia {s.relevance:.2f}" if detail != "operator" else ""))
            if st.toggle("Ver evidencia" if lang == "es" else "Show evidence", key=f"ev-{key}-{i}"):
                st.text(s.excerpt)
                if user.can("sources.download"):
                    _download_original(s.version_id, f"dl-{key}-{i}")
    if answer.confidence and detail != "operator":
        st.caption("Confianza: " + ", ".join(f"{k}={v}" for k, v in answer.confidence.components.items())
                   + ("; " + "; ".join(answer.confidence.reasons) if answer.confidence.reasons else ""))
    if detail in {"engineering", "admin"} and user.can("debug.view") and answer.debug.get("candidates"):
        with st.expander("Detalle técnico de recuperación"):
            st.dataframe(answer.debug["candidates"], hide_index=True)
            st.caption(f"Fragmentos elegibles: {answer.debug.get('eligible_chunks')} · léxicos: "
                       f"{answer.debug.get('lexical')} · vectoriales: {answer.debug.get('vector')}")
    if detail == "admin":
        st.caption(f"Modo: {answer.mode} · Latencia: {answer.latency_ms} ms · CID: {answer.correlation_id}")
    st.caption(tr("ans.disclaimer"))
    _actions(answer, user, key)


def _download_original(version_id: str, key: str) -> None:
    c = container()
    try:
        name, data = c.knowledge.original_file(c_user(), version_id, cid())
    except Exception:  # noqa: BLE001 - sin archivo original (contenido de texto) o sin permiso
        return
    st.download_button("Descargar original", data=data, file_name=name, key=key)


def c_user() -> AuthenticatedUser:
    return st.session_state["user"]


def _actions(answer: Answer, user: AuthenticatedUser, key: str) -> None:
    c = container()
    cols = st.columns(4)
    with cols[0]:
        st.download_button(tr("ans.evidence"), data=_evidence_text(answer).encode("utf-8"),
                           file_name=f"evidencia_{answer.query_id or key}.txt", key=f"evd-{key}")
    with cols[1]:
        if st.button("👍 " + tr("ans.helpful"), key=f"up-{key}"):
            run_safely(lambda: c.feedback.rate(user, answer.query_id, True), "Gracias por tu feedback.")
    with cols[2]:
        if st.button("👎 " + tr("ans.not_helpful"), key=f"down-{key}"):
            run_safely(lambda: c.feedback.rate(user, answer.query_id, False), "Feedback registrado.")
    with cols[3]:
        with st.popover(tr("ans.copy")):
            st.code(answer.as_text(), language=None)
    with st.expander(tr("ans.report")):
        with st.form(f"report-{key}"):
            comment = st.text_area("¿Qué es incorrecto?" if answer.language == "es" else "What is wrong?",
                                   max_chars=2000)
            proposed = st.text_area("Respuesta correcta propuesta (opcional; será revisada)", max_chars=4000)
            if st.form_submit_button("Enviar a revisión"):
                run_safely(lambda: c.feedback.report_incorrect(user, answer.query_id, answer.as_text(), comment,
                                                               proposed, cid()),
                           "Enviado a la bandeja de revisión. No se usará hasta ser aprobado.")
    if user.can("incident.create"):
        with st.expander(tr("ans.escalate_btn")):
            _incident_form(answer, user, key)


def _incident_form(answer: Answer, user: AuthenticatedUser, key: str) -> None:
    c = container()
    areas = c.settings.get("escalation.areas", ["MES Support"])
    default_urgency = Urgency.HIGH.value if (answer.sentiment and answer.sentiment.label == "Urgent") \
        or answer.safety_stop else Urgency.MEDIUM.value
    with st.form(f"inc-{key}"):
        a, b, d = st.columns(3)
        work_order = a.text_input("Work Order (opcional)", max_chars=64)
        serial = b.text_input("Serial (opcional)", max_chars=64)
        assembly = d.text_input("Ensamble (opcional)", max_chars=64)
        e, f = st.columns(2)
        station = e.text_input("Estación", max_chars=80)
        operation = f.text_input("Operación", max_chars=80)
        error = st.text_area("Mensaje de error exacto", max_chars=2000)
        diagnosis = st.text_area("Diagnóstico preliminar", max_chars=3000,
                                 value="Sin evidencia aprobada suficiente." if not answer.answered else "")
        g, h = st.columns(2)
        urgency = g.selectbox("Urgencia", Urgency.values(), index=Urgency.values().index(default_urgency))
        area = h.selectbox("Área sugerida", areas)
        shot = st.file_uploader("Captura de pantalla (PNG/JPG, máx. 5 MB)", type=["png", "jpg", "jpeg"])
        if st.form_submit_button("Crear incidente", type="primary"):
            data = IncidentInput(question=answer.question, answer=answer.as_text(), work_order=work_order,
                                 serial_number=serial, assembly=assembly, station=station, operation=operation,
                                 error_message=error, preliminary_diagnosis=diagnosis, urgency=urgency,
                                 suggested_area=area,
                                 sources="; ".join(f"{s.doc_code} v{s.version_label} ({s.section})"
                                                   for s in answer.sources))
            attachment = (shot.name, shot.getvalue()) if shot else None
            result = run_safely(lambda: c.incidents.create(user, data, attachment, cid()))
            if result:
                st.success(f"Incidente creado: {result[1]}")
