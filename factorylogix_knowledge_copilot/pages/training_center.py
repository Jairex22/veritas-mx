"""Knowledge Training Center: carga, revisión, aprobación, publicación, versiones, rollback y Q&A."""
from __future__ import annotations

from datetime import timedelta

import streamlit as st

from core.utils import today
from models.domain import FL_MODULES, Classification, DocStatus, SourceType
from schemas.validation import DocumentMetadataInput
from services.knowledge_service import RAG_TRAINING_NOTICE_EN, RAG_TRAINING_NOTICE_ES
from ui.components import demo_banner, header, md
from ui.state import cid, container, guard_any, lang, run_safely, tr


def _metadata_form(prefix: str, defaults: dict | None = None, lock_code: bool = False) -> DocumentMetadataInput:
    c = container()
    d = defaults or {}
    policies = c.knowledge.retention_options()
    col1, col2, col3 = st.columns(3)
    doc_code = col1.text_input("Código del documento*", value=d.get("doc_code", ""), disabled=lock_code,
                               key=f"{prefix}-code", max_chars=60)
    title = col2.text_input("Título*", value=d.get("title", ""), key=f"{prefix}-title", max_chars=200)
    source_type = col3.selectbox("Tipo de fuente*", SourceType.values(),
                                 index=SourceType.values().index(d.get("source_type", "Procedure")),
                                 key=f"{prefix}-type")
    description = st.text_area("Descripción*", value=d.get("description", ""), key=f"{prefix}-desc", max_chars=1000)
    col1, col2, col3 = st.columns(3)
    owner = col1.text_input("Propietario*", value=d.get("owner", ""), key=f"{prefix}-owner")
    approver = col2.text_input("Aprobador designado*", value=d.get("approver", ""), key=f"{prefix}-approver")
    area = col3.text_input("Área*", value=d.get("area", ""), key=f"{prefix}-area")
    col1, col2, col3, col4, col5 = st.columns(5)
    customer = col1.text_input("Cliente", value=d.get("customer", ""), key=f"{prefix}-cust")
    product = col2.text_input("Producto", value=d.get("product", ""), key=f"{prefix}-prod")
    line = col3.text_input("Línea", value=d.get("line", ""), key=f"{prefix}-line")
    process = col4.text_input("Proceso", value=d.get("process", ""), key=f"{prefix}-proc")
    station = col5.text_input("Estación", value=d.get("station", ""), key=f"{prefix}-station")
    col1, col2, col3, col4 = st.columns(4)
    module = col1.selectbox("Módulo FactoryLogix*", FL_MODULES,
                            index=FL_MODULES.index(d.get("fl_module", "General")) if d.get("fl_module") in FL_MODULES
                            else FL_MODULES.index("General"), key=f"{prefix}-mod")
    classification = col2.selectbox("Clasificación*", Classification.values(),
                                    index=Classification.values().index(d.get("classification", "Internal")),
                                    key=f"{prefix}-class")
    retention = col3.selectbox("Política de retención*", policies,
                               index=policies.index(d["retention_policy"]) if d.get("retention_policy") in policies
                               else 0, key=f"{prefix}-ret")
    language = col4.selectbox("Idioma", ["es", "en"], index=0 if d.get("language", "es") == "es" else 1,
                              key=f"{prefix}-lang")
    col1, col2, col3 = st.columns(3)
    effective = col1.date_input("Fecha efectiva*", value=today(), key=f"{prefix}-eff")
    review = col2.date_input("Fecha de revisión*", value=today() + timedelta(days=365), key=f"{prefix}-rev")
    has_exp = col3.checkbox("Tiene fecha de expiración", key=f"{prefix}-hasexp")
    expiration = col3.date_input("Fecha de expiración", value=today() + timedelta(days=730), key=f"{prefix}-exp",
                                 disabled=not has_exp)
    tags = st.text_input("Etiquetas (separadas por coma)", value=d.get("tags", ""), key=f"{prefix}-tags")
    note = st.text_input("Nota de cambio", key=f"{prefix}-note", max_chars=500)
    return DocumentMetadataInput(
        doc_code=doc_code, title=title, description=description, source_type=source_type, owner=owner,
        approver=approver, area=area, fl_module=module, classification=classification, retention_policy=retention,
        customer=customer, product=product, line=line, process=process, station=station, tags=tags,
        language=language, effective_date=effective.isoformat(), review_date=review.isoformat(),
        expiration_date=expiration.isoformat() if has_exp else "", change_note=note)


def _show_report(report) -> None:
    st.success(f"Versión {report.version_label} creada como Draft ({report.chunk_count} fragmentos).")
    for w in report.warnings:
        st.warning(w)
    if report.duplicates:
        st.warning("Duplicado exacto detectado: " + ", ".join(f"{d['doc_code']} v{d['version_label']} ({d['status']})"
                                                              for d in report.duplicates))
    if report.near_duplicates:
        st.warning("Posibles duplicados (similitud ≥ umbral): " + ", ".join(
            f"{d['doc_code']} ({d['similarity']:.0%})" for d in report.near_duplicates))
    if report.injection_matches:
        st.error("Posible prompt injection en el documento: " + ", ".join(report.injection_matches) +
                 ". El contenido se trata como datos y requiere confirmación explícita del aprobador.")
    with st.expander("Revisar texto extraído"):
        st.text(report.preview)


def _upload_tab() -> None:
    c = container()
    user = guard_any("knowledge.upload", "knowledge.approve")
    if not user.can("knowledge.upload"):
        st.info("Tu rol no carga documentos; puedes revisar, aprobar y publicar.")
        return
    exts = [e.lstrip(".") for e in c.settings.get("ingestion.allowed_extensions", [])]
    st.caption(f"Formatos permitidos: {', '.join(exts)} · máximo {c.settings.get('ingestion.max_file_mb')} MB. "
               "Imágenes solo si OCR está disponible.")
    with st.form("upload-new"):
        file = st.file_uploader("Archivo", type=exts)
        meta = _metadata_form("new")
        submitted = st.form_submit_button("Cargar y extraer", type="primary")
    if submitted:
        if not file:
            st.error("Selecciona un archivo.")
            return
        report = run_safely(lambda: c.knowledge.ingest_file(user, file.name, file.getvalue(), meta, None, cid()))
        if report:
            _show_report(report)


def _new_version_tab() -> None:
    c = container()
    user = guard_any("knowledge.upload", "knowledge.approve")
    if not user.can("knowledge.upload"):
        st.info("Tu rol no carga documentos; puedes revisar, aprobar y publicar.")
        return
    catalog = c.knowledge.catalog(user)
    if not catalog:
        st.info("No hay documentos.")
        return
    options = {f"{r['doc_code']} · {r['title']}": r for r in catalog}
    selected = options[st.selectbox("Documento", list(options), key="nv-doc")]
    exts = [e.lstrip(".") for e in c.settings.get("ingestion.allowed_extensions", [])]
    with st.form("upload-version"):
        file = st.file_uploader("Archivo de la nueva versión", type=exts)
        meta = _metadata_form("nv", selected, lock_code=True)
        submitted = st.form_submit_button("Cargar nueva versión", type="primary")
    if submitted:
        if not file:
            st.error("Selecciona un archivo.")
            return
        meta.doc_code = selected["doc_code"]
        report = run_safely(lambda: c.knowledge.ingest_file(user, file.name, file.getvalue(), meta,
                                                            selected["id"], cid()))
        if report:
            _show_report(report)


def _review_tab() -> None:
    c = container()
    user = guard_any("knowledge.upload", "knowledge.approve")
    pending = c.knowledge.docs.versions_by_status(DocStatus.DRAFT.value) + \
        c.knowledge.docs.versions_by_status(DocStatus.UNDER_REVIEW.value)
    pending = [v for v in pending if v["classification"] in user.clearance]
    if not pending:
        st.info("No hay versiones en Draft o Under Review.")
        return
    for v in pending:
        with st.container(border=True):
            st.markdown(f"**{md(v['doc_code'])}** v{v['version_label']} · {md(v['title'])} · "
                        f"`{v['status']}` · cargado por {md(v['created_by'])}")
            if v["duplicate_of"]:
                st.warning(f"Duplicado exacto de {v['duplicate_of']}")
            if v["injection_flags"]:
                st.error(f"Posible prompt injection: {v['injection_flags']}")
            with st.expander("Texto extraído"):
                st.text(c.knowledge.version_text(user, v["id"])[:20000])
            reason = st.text_input(tr("common.reason"), key=f"reason-{v['id']}", max_chars=500)
            cols = st.columns(4)
            if v["status"] == DocStatus.DRAFT.value and cols[0].button("Enviar a revisión", key=f"sub-{v['id']}"):
                run_safely(lambda: c.knowledge.submit_for_review(user, v["id"], cid()), "Enviado a revisión.")
                st.rerun()
            if v["status"] == DocStatus.UNDER_REVIEW.value and user.can("knowledge.approve"):
                ack = True
                if v["injection_flags"]:
                    ack = cols[3].checkbox("Confirmo que revisé las instrucciones sospechosas y se tratarán como datos",
                                           key=f"ack-{v['id']}")
                if cols[0].button("Aprobar", key=f"apr-{v['id']}", type="primary"):
                    if run_safely(lambda: c.knowledge.approve(user, v["id"], reason, ack, cid()) or True,
                                  "Versión aprobada. Publícala desde la pestaña Publicar."):
                        st.rerun()
                if cols[1].button("Rechazar", key=f"rej-{v['id']}"):
                    if run_safely(lambda: c.knowledge.reject(user, v["id"], reason, cid()) or True, "Rechazada."):
                        st.rerun()
                if cols[2].button("Regresar a Draft", key=f"ret-{v['id']}"):
                    if run_safely(lambda: c.knowledge.return_to_draft(user, v["id"], reason, cid()) or True):
                        st.rerun()


def _publish_tab() -> None:
    c = container()
    user = guard_any("knowledge.upload", "knowledge.approve")
    approved = [v for v in c.knowledge.docs.versions_by_status(DocStatus.APPROVED.value)
                if v["classification"] in user.clearance]
    catalog = {r["id"]: r for r in c.knowledge.docs.catalog()}
    unpublished = [v for v in approved if catalog.get(v["document_id"], {}).get("published_version_id") != v["id"]]
    if not unpublished:
        st.info("No hay versiones aprobadas pendientes de publicar.")
        return
    for v in unpublished:
        with st.container(border=True):
            st.markdown(f"**{md(v['doc_code'])}** v{v['version_label']} · {md(v['title'])} · aprobada por "
                        f"{md(v['decided_by'] or '')}")
            if st.button("Ejecutar pruebas previas", key=f"chk-{v['id']}"):
                checks = run_safely(lambda: c.knowledge.prepublish_checks(v["id"]))
                if checks:
                    st.dataframe([{"Prueba": ch.name, "Resultado": "✔" if ch.ok else "✖",
                                   "Crítica": "Sí" if ch.critical else "No", "Detalle": ch.detail} for ch in checks],
                                 hide_index=True)
            reason = st.text_input("Nota de publicación", key=f"pubr-{v['id']}")
            if user.can("knowledge.publish") and st.button("Publicar versión", key=f"pub-{v['id']}", type="primary"):
                if run_safely(lambda: c.knowledge.publish(user, v["id"], reason, cid()) or True, "Publicada."):
                    st.rerun()


def _versions_tab() -> None:
    c = container()
    user = guard_any("knowledge.upload", "knowledge.approve")
    catalog = c.knowledge.catalog(user)
    if not catalog:
        return
    options = {f"{r['doc_code']} · {r['title']}": r for r in catalog}
    doc = options[st.selectbox("Documento", list(options), key="ver-doc")]
    versions = c.knowledge.versions(user, doc["id"])
    st.dataframe([{"Versión": v["version_label"], "Estado": v["status"], "Publicada": "★" if v["id"] ==
                   doc["published_version_id"] else "", "Efectiva": v["effective_date"], "Revisión": v["review_date"],
                   "Expira": v["expiration_date"] or "—", "Creada por": v["created_by"], "Decidida por": v["decided_by"],
                   "Nota": v["change_note"]} for v in versions], hide_index=True)
    labels = {f"v{v['version_label']} ({v['status']})": v for v in versions}
    if len(versions) >= 2:
        st.markdown("**Comparar versiones**")
        a, b = st.columns(2)
        old = labels[a.selectbox("Versión anterior", list(labels), index=1, key="diff-a")]
        new = labels[b.selectbox("Versión nueva", list(labels), index=0, key="diff-b")]
        if st.button("Comparar"):
            diff = run_safely(lambda: c.knowledge.diff_versions(user, old["id"], new["id"]))
            if diff:
                st.code(diff, language="diff")
    rollback_targets = {k: v for k, v in labels.items() if v["status"] == DocStatus.ARCHIVED.value and v["ever_approved"]}
    if rollback_targets and user.can("knowledge.publish"):
        st.markdown("**Rollback a versión anterior aprobada**")
        target = rollback_targets[st.selectbox("Versión destino", list(rollback_targets), key="rb-target")]
        reason = st.text_input("Motivo del rollback", key="rb-reason")
        if st.button("Ejecutar rollback", type="primary"):
            if run_safely(lambda: c.knowledge.rollback(user, doc["id"], target["id"], reason, cid()) or True,
                          "Rollback aplicado."):
                st.rerun()


def _qa_tab() -> None:
    c = container()
    user = guard_any("knowledge.upload", "knowledge.approve")
    st.caption("Las Q&A propuestas requieren aprobación de otra persona y se publican como fuente 'Approved Q&A'.")
    if user.can("knowledge.edit"):
        with st.form("qa-new"):
            question = st.text_input("Pregunta", max_chars=500)
            answer = st.text_area("Respuesta aprobable (basada en procedimiento vigente)", max_chars=4000)
            a, b = st.columns(2)
            module = a.selectbox("Módulo", FL_MODULES, index=FL_MODULES.index("General"))
            classification = b.selectbox("Clasificación", Classification.values(), index=1)
            if st.form_submit_button("Proponer Q&A"):
                run_safely(lambda: c.knowledge.propose_qa(user, question, answer, module, classification, None, cid()),
                           "Q&A enviada a revisión.")
    pending = c.knowledge.qa.list(DocStatus.UNDER_REVIEW.value)
    for item in pending:
        with st.container(border=True):
            st.markdown(f"**{md(item['question'])}**")
            st.text(item["answer"])
            st.caption(f"Propuesta por {item['created_by']} · {item['fl_module']} · {item['classification']}")
            reason = st.text_input(tr("common.reason"), key=f"qar-{item['id']}")
            a, b = st.columns(2)
            if user.can("knowledge.approve") and a.button("Aprobar y publicar", key=f"qaa-{item['id']}"):
                if run_safely(lambda: c.knowledge.approve_qa(user, item["id"], reason, cid()), "Q&A publicada."):
                    st.rerun()
            if user.can("knowledge.approve") and b.button("Rechazar", key=f"qaj-{item['id']}"):
                if run_safely(lambda: c.knowledge.reject_qa(user, item["id"], reason, cid()) or True, "Rechazada."):
                    st.rerun()
    if user.can("export.data"):
        if st.button("Preparar exportación JSONL de Q&A aprobadas"):
            data = run_safely(lambda: c.knowledge.export_approved_jsonl(user, cid()))
            if data is not None:
                st.download_button("Descargar JSONL", data=data.encode("utf-8"), file_name="qa_aprobadas.jsonl")
                st.caption("Exportación para un posible fine-tuning futuro. No se ejecuta fine-tuning automático.")


def _maintenance_tab() -> None:
    c = container()
    user = guard_any("knowledge.upload", "knowledge.approve")
    counts = c.knowledge.chunks.counts()
    st.metric("Fragmentos indexados", counts["chunks"])
    st.caption(f"Modelo de embeddings: {c.knowledge.embedder.name}")
    if user.can("knowledge.publish") and st.button("Reindexar todo"):
        result = run_safely(lambda: c.knowledge.reindex_all(user, cid()))
        if result:
            st.success(f"Reindexadas {result['versions']} versiones ({result['chunks']} fragmentos).")


def render() -> None:
    guard_any("knowledge.upload", "knowledge.approve")
    header(tr("nav.training"), "Agregar, revisar, aprobar y publicar conocimiento recuperable.")
    demo_banner()
    st.info(RAG_TRAINING_NOTICE_EN if lang() == "en" else RAG_TRAINING_NOTICE_ES)
    tabs = st.tabs(["Cargar documento", "Nueva versión", "Revisión y aprobación", "Publicar", "Versiones y rollback",
                    "Q&A aprobadas", "Reindexación"])
    with tabs[0]:
        _upload_tab()
    with tabs[1]:
        _new_version_tab()
    with tabs[2]:
        _review_tab()
    with tabs[3]:
        _publish_tab()
    with tabs[4]:
        _versions_tab()
    with tabs[5]:
        _qa_tab()
    with tabs[6]:
        _maintenance_tab()
