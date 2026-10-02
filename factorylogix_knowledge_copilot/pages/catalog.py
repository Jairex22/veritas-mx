"""Catálogo de datos: metadatos completos, edición controlada, activación y vigencia."""
from __future__ import annotations

import streamlit as st

from core.utils import parse_date
from models.domain import FL_MODULES, Classification, SourceType
from services.export_service import to_csv_bytes
from ui.components import demo_banner, header
from ui.state import cid, container, guard, run_safely, tr

COLUMNS = ["doc_code", "title", "source_type", "owner", "approver", "area", "customer", "product", "line", "process",
           "station", "fl_module", "classification", "retention_policy", "published_version", "published_status",
           "latest_version", "latest_status", "effective_date", "review_date", "expiration_date", "is_active",
           "is_demo", "tags", "created_at", "content_hash"]


def render() -> None:
    user = guard("governance.view")
    c = container()
    header(tr("nav.catalog"), "Catálogo de documentos con metadatos obligatorios y estado.")
    demo_banner()
    catalog = c.knowledge.catalog(user)
    a, b, d = st.columns(3)
    status = a.selectbox("Estado", ["(todos)", "Approved", "Draft", "Under Review", "Rejected", "Expired", "Archived"])
    classification = b.selectbox("Clasificación", ["(todas)"] + Classification.values())
    text = d.text_input("Buscar", max_chars=80)
    rows = []
    for r in catalog:
        state = r["published_status"] or r["latest_status"]
        if status != "(todos)" and state != status and r["latest_status"] != status:
            continue
        if classification != "(todas)" and r["classification"] != classification:
            continue
        if text and text.lower() not in f"{r['doc_code']} {r['title']} {r['tags']}".lower():
            continue
        rows.append({k: r.get(k) for k in COLUMNS})
    st.dataframe(rows, hide_index=True)
    if user.can("export.data"):
        st.download_button(tr("common.export_csv"), data=to_csv_bytes(rows, COLUMNS), file_name="catalogo.csv")

    if not catalog or not (user.can("governance.manage") or user.can("knowledge.edit") or
                           user.can("knowledge.publish")):
        return
    st.markdown("### Editar documento")
    options = {f"{r['doc_code']} · {r['title']}": r for r in catalog}
    doc = options[st.selectbox("Documento", list(options), key="cat-doc")]
    with st.form("meta-edit"):
        col1, col2, col3 = st.columns(3)
        changes = {
            "title": col1.text_input("Título", doc["title"]),
            "owner": col2.text_input("Propietario", doc["owner"]),
            "approver": col3.text_input("Aprobador", doc["approver"]),
            "description": st.text_area("Descripción", doc["description"]),
            "area": col1.text_input("Área", doc["area"]),
            "customer": col2.text_input("Cliente", doc["customer"]),
            "product": col3.text_input("Producto", doc["product"]),
            "line": col1.text_input("Línea", doc["line"]),
            "process": col2.text_input("Proceso", doc["process"]),
            "station": col3.text_input("Estación", doc["station"]),
            "fl_module": col1.selectbox("Módulo", FL_MODULES, index=FL_MODULES.index(doc["fl_module"])
                                        if doc["fl_module"] in FL_MODULES else 0),
            "source_type": col2.selectbox("Tipo", SourceType.values(), index=SourceType.values().index(
                doc["source_type"])),
            "classification": col3.selectbox("Clasificación", Classification.values(),
                                             index=Classification.values().index(doc["classification"])),
            "retention_policy": col1.selectbox("Retención", c.knowledge.retention_options(),
                                               index=c.knowledge.retention_options().index(doc["retention_policy"])
                                               if doc["retention_policy"] in c.knowledge.retention_options() else 0),
            "tags": col2.text_input("Etiquetas", doc["tags"]),
        }
        reason = st.text_input("Motivo del cambio (obligatorio)")
        if st.form_submit_button("Guardar metadatos"):
            changed = run_safely(lambda: c.knowledge.update_metadata(user, doc["id"], changes, reason, cid()))
            if changed is not None:
                st.success("Campos actualizados: " + (", ".join(changed) or "ninguno"))

    if doc.get("published_version_id") and user.can("governance.manage"):
        st.markdown("### Vigencia de la versión publicada")
        with st.form("validity"):
            a, b, d = st.columns(3)
            eff = a.date_input("Efectiva", parse_date(doc["effective_date"]))
            rev = b.date_input("Revisión", parse_date(doc["review_date"]))
            has_exp = d.checkbox("Con expiración", value=bool(doc["expiration_date"]))
            exp = d.date_input("Expiración", parse_date(doc["expiration_date"]) or rev, disabled=not has_exp)
            reason = st.text_input("Motivo", key="val-reason")
            if st.form_submit_button("Actualizar vigencia"):
                run_safely(lambda: c.knowledge.update_version_dates(
                    user, doc["published_version_id"], eff.isoformat(), rev.isoformat(),
                    exp.isoformat() if has_exp else "", reason, cid()), "Vigencia actualizada.")

    if user.can("knowledge.publish"):
        st.markdown("### Activación")
        reason = st.text_input("Motivo de activación/desactivación", key="act-reason")
        label = "Desactivar documento" if doc["is_active"] else "Activar documento"
        if st.button(label):
            if run_safely(lambda: c.knowledge.set_active(user, doc["id"], not doc["is_active"], reason, cid()) or True,
                          "Estado actualizado."):
                st.rerun()
