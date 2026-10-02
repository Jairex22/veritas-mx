"""Página de Fuentes: documentos aprobados y vigentes visibles para el rol, con evidencia."""
from __future__ import annotations

import streamlit as st

from ui.components import demo_banner, header, md
from ui.state import cid, container, guard, run_safely, tr


def render() -> None:
    user = guard("sources.view")
    c = container()
    header(tr("nav.sources"), "Documentos publicados, aprobados y vigentes que el asistente puede usar para tu rol.")
    demo_banner()
    catalog = [r for r in c.knowledge.catalog(user) if r.get("published_version_id") and r.get("is_active")
               and r.get("published_status") == "Approved"]
    if not catalog:
        st.info("No hay documentos publicados para tu rol.")
        return
    rows = [{"Código": r["doc_code"], "Título": r["title"], "Tipo": r["source_type"], "Módulo": r["fl_module"],
             "Clasificación": r["classification"], "Versión": r["published_version"],
             "Revisión": r["review_date"], "Expira": r["expiration_date"] or "—",
             "DEMO": "Sí" if r["is_demo"] else "No"} for r in catalog]
    st.dataframe(rows, hide_index=True)
    options = {f"{r['doc_code']} · {r['title']}": r for r in catalog}
    selected = st.selectbox("Consultar evidencia", list(options))
    doc = options[selected]
    st.markdown(f"**{md(doc['title'])}** — {md(doc['description'])}")
    st.caption(f"Propietario: {doc['owner']} · Aprobador: {doc['approver']} · Área: {doc['area']} · "
               f"Versión {doc['published_version']} · Clasificación {doc['classification']}")
    chunks = c.knowledge.chunks.for_version(doc["published_version_id"])
    for chunk in chunks:
        page = f" · pág. {chunk['page']}" if chunk["page"] else ""
        with st.expander(f"{chunk['section'] or 'Fragmento'}{page}"):
            text, removed = c.engine.detector.strip_suspicious(chunk["text"]) if chunk["injection_flag"] \
                else (chunk["text"], 0)
            if removed:
                st.warning("Se ocultaron instrucciones sospechosas detectadas en este fragmento.")
            st.text(text)
    if user.can("sources.download"):
        if st.button("Preparar descarga del original"):
            result = run_safely(lambda: c.knowledge.original_file(user, doc["published_version_id"], cid()))
            if result:
                st.download_button("Descargar original", data=result[1], file_name=result[0])
