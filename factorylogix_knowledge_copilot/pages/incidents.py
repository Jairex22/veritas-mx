"""Incidentes y paquetes de escalamiento."""
from __future__ import annotations

import streamlit as st

from models.domain import IncidentStatus, Urgency
from schemas.validation import IncidentInput
from ui.components import demo_banner, header, md
from ui.state import cid, container, guard, run_safely, tr


def _create_form(user) -> None:
    c = container()
    with st.expander("Crear incidente manual"):
        with st.form("inc-manual"):
            question = st.text_area("Descripción / pregunta", max_chars=2000)
            a, b, d = st.columns(3)
            work_order = a.text_input("Work Order", max_chars=64)
            serial = b.text_input("Serial", max_chars=64)
            assembly = d.text_input("Ensamble", max_chars=64)
            e, f = st.columns(2)
            station = e.text_input("Estación", max_chars=80)
            operation = f.text_input("Operación", max_chars=80)
            error = st.text_area("Mensaje de error", max_chars=2000)
            g, h = st.columns(2)
            urgency = g.selectbox("Urgencia", Urgency.values(), index=1)
            area = h.selectbox("Área sugerida", c.settings.get("escalation.areas", ["MES Support"]))
            shot = st.file_uploader("Captura (PNG/JPG)", type=["png", "jpg", "jpeg"])
            if st.form_submit_button("Crear", type="primary"):
                data = IncidentInput(question=question, work_order=work_order, serial_number=serial,
                                     assembly=assembly, station=station, operation=operation, error_message=error,
                                     urgency=urgency, suggested_area=area)
                result = run_safely(lambda: c.incidents.create(user, data, (shot.name, shot.getvalue())
                                                               if shot else None, cid()))
                if result:
                    st.success(f"Incidente creado: {result[1]}")


def render() -> None:
    user = guard("incident.create")
    c = container()
    header(tr("nav.incidents"), "Paquetes de escalamiento para MES, Producto, Calidad y supervisores.")
    demo_banner()
    _create_form(user)
    status = st.selectbox("Filtrar por estado", ["(todos)"] + IncidentStatus.values())
    items = c.incidents.list(user, "" if status == "(todos)" else status)
    st.dataframe([{k: i[k] for k in ("code", "created_at", "created_by", "urgency", "status", "suggested_area",
                                     "work_order", "serial_number", "station")} for i in items], hide_index=True)
    if items and st.button("Preparar exportación CSV"):
        data = run_safely(lambda: c.incidents.export_csv(user, items, cid()))
        if data:
            st.download_button(tr("common.export_csv"), data=data, file_name="incidentes.csv")
    if not items:
        return
    options = {f"{i['code']} · {i['status']} · {i['urgency']}": i for i in items}
    item = options[st.selectbox("Detalle", list(options))]
    with st.container(border=True):
        st.markdown(f"### {md(item['code'])} · {md(item['status'])}")
        st.markdown(f"**Urgencia:** {md(item['urgency'])} · **Área:** {md(item['suggested_area'])} · "
                    f"**Creado por:** {md(item['created_by'])} ({md(item['created_by_role'])})")
        st.markdown(f"**WO:** {md(item['work_order'] or '—')} · **Serial:** {md(item['serial_number'] or '—')} · "
                    f"**Ensamble:** {md(item['assembly'] or '—')} · **Estación:** {md(item['station'] or '—')} · "
                    f"**Operación:** {md(item['operation'] or '—')}")
        for label, key in (("Mensaje de error", "error_message"), ("Pregunta", "question"), ("Respuesta", "answer"),
                           ("Fuentes", "sources"), ("Diagnóstico preliminar", "preliminary_diagnosis"),
                           ("Notas", "notes")):
            if item[key]:
                st.markdown(f"**{label}**")
                st.text(item[key])
        attachment = run_safely(lambda: c.incidents.attachment(user, item["id"]))
        if attachment:
            st.image(attachment[1], caption=attachment[0], width=420)
        report = None
        if st.button("Preparar reporte imprimible"):
            report = run_safely(lambda: c.incidents.printable(user, item["id"], c.settings_service.branding()))
        if report:
            st.download_button("Descargar reporte imprimible (HTML)", data=report.encode("utf-8"),
                               file_name=f"{item['code']}.html", mime="text/html")
        if user.can("incident.manage"):
            with st.form("inc-update"):
                new_status = st.selectbox("Nuevo estado", IncidentStatus.values(),
                                          index=IncidentStatus.values().index(item["status"]))
                notes = st.text_area("Nota de seguimiento", max_chars=2000)
                if st.form_submit_button("Actualizar"):
                    if run_safely(lambda: c.incidents.update_status(user, item["id"], new_status, notes, cid())
                                  or True, "Actualizado."):
                        st.rerun()
        if c.incidents.notifier.enabled:
            with st.form("inc-mail"):
                to = st.text_input("Enviar por correo interno a")
                confirm = st.checkbox("Confirmo el envío de este paquete por correo")
                if st.form_submit_button("Enviar correo"):
                    run_safely(lambda: c.incidents.email(user, item["id"], to, confirm, cid()), "Correo enviado.")
        else:
            st.caption("Envío de correo desactivado (requiere configuración explícita en settings.yaml).")
