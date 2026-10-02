"""Gobierno de datos: vigencia, propietarios, matriz de acceso, retención, linaje y registros."""
from __future__ import annotations

import streamlit as st

from core.utils import today
from governance.lifecycle import SOURCE_PRIORITY_TEXT
from governance.policies import access_matrix_rows, retention_actions, validity_findings
from services.export_service import to_csv_bytes
from ui.components import demo_banner, header, md
from ui.state import cid, container, guard, run_safely, tr


def _findings_tab() -> None:
    c = container()
    findings = validity_findings(c.knowledge.docs.catalog(), today(), int(c.settings.get("rag.review_soon_days", 30)))
    critical = [f for f in findings if f.severity == "critical"]
    warning = [f for f in findings if f.severity == "warning"]
    a, b, d = st.columns(3)
    a.metric("Hallazgos críticos", len(critical))
    b.metric("Advertencias", len(warning))
    d.metric("Documentos", len(c.knowledge.docs.catalog()))
    rows = [{"Severidad": f.severity, "Código": f.doc_code, "Título": f.title, "Hallazgo": f.issue} for f in findings]
    st.dataframe(rows, hide_index=True)
    st.download_button("Exportar reporte de fuentes (CSV)", data=to_csv_bytes(rows), file_name="reporte_fuentes.csv")
    user = guard("governance.view")
    if user.can("governance.manage") and st.button("Ejecutar validación de vigencia ahora"):
        result = run_safely(lambda: c.knowledge.run_lifecycle(user, cid()))
        if result is not None:
            st.success(f"Versiones marcadas como Expired: {result['expired']}")


def _access_tab() -> None:
    c = container()
    st.markdown("**Matriz de acceso por clasificación** (config/settings.yaml → access_matrix)")
    st.dataframe(access_matrix_rows(c.policy.clearance), hide_index=True)
    st.markdown("**Orden de prioridad de las fuentes**")
    st.markdown("\n".join(f"- {line}" for line in SOURCE_PRIORITY_TEXT))
    st.caption("Si dos fuentes aprobadas se contradicen, el asistente no elige ninguna: muestra el conflicto y "
               "solicita escalamiento.")


def _retention_tab() -> None:
    c = container()
    user = guard("governance.view")
    policies = c.settings.get("governance.retention_policies", {})
    st.dataframe([{"Política": k, **v} for k, v in policies.items()], hide_index=True)
    actions = retention_actions(c.knowledge.docs.all_versions(), policies, today())
    st.markdown(f"**Versiones elegibles para eliminación por retención:** {len(actions)}")
    if actions:
        st.dataframe(actions, hide_index=True)
    if not user.can("documents.delete"):
        return
    st.markdown("**Eliminación autorizada de documento** (borra archivos, texto y fragmentos; conserva lápida y "
                "auditoría)")
    catalog = [r for r in c.knowledge.docs.catalog() if not (r["is_active"] and r["published_version_id"])]
    if not catalog:
        st.caption("Solo se pueden eliminar documentos desactivados o sin versión publicada.")
        return
    options = {f"{r['doc_code']} · {r['title']}": r for r in catalog}
    doc = options[st.selectbox("Documento", list(options), key="del-doc")]
    reason = st.text_input("Motivo de eliminación (obligatorio)", key="del-reason")
    confirm = st.checkbox("Confirmo la eliminación autorizada de este documento", key="del-confirm")
    if st.button("Eliminar", disabled=not confirm):
        if run_safely(lambda: c.knowledge.delete_document(user, doc["id"], reason, cid()) or True, "Eliminado."):
            st.rerun()


def _lineage_tab() -> None:
    c = container()
    user = guard("governance.view")
    catalog = c.knowledge.catalog(user)
    if not catalog:
        return
    options = {f"{r['doc_code']} · {r['title']}": r for r in catalog}
    doc = options[st.selectbox("Documento", list(options), key="lin-doc")]
    versions = c.knowledge.versions(user, doc["id"])
    for v in versions:
        chunks = c.knowledge.chunks.for_version(v["id"])
        uses = c.db.scalar("SELECT COUNT(*) FROM answer_sources WHERE version_id = ?", (v["id"],), default=0)
        st.markdown(f"📄 **{md(doc['doc_code'])}** → v{v['version_label']} (`{v['status']}`, hash "
                    f"`{v['content_hash'][:12]}…`) → **{len(chunks)}** fragmentos → **{uses}** respuestas citaron "
                    f"esta versión")
    query_id = st.text_input("Rastrear una respuesta por Query ID", key="lin-q")
    if query_id:
        st.dataframe(c.chat.query_log.sources_for_query(query_id.strip()), hide_index=True)


def _logs_tab() -> None:
    c = container()
    st.markdown("**Registro de aprobaciones**")
    st.dataframe(c.knowledge.docs.approvals(limit=300), hide_index=True)
    st.markdown("**Registro de cambios de metadatos**")
    st.dataframe(c.knowledge.docs.metadata_changes(limit=300), hide_index=True)


def render() -> None:
    guard("governance.view")
    header(tr("nav.governance"), "Vigencia, propietarios, clasificación, retención, linaje y aprobaciones.")
    demo_banner()
    tabs = st.tabs(["Vigencia y propietarios", "Acceso y prioridad", "Retención", "Linaje", "Registros"])
    with tabs[0]:
        _findings_tab()
    with tabs[1]:
        _access_tab()
    with tabs[2]:
        _retention_tab()
    with tabs[3]:
        _lineage_tab()
    with tabs[4]:
        _logs_tab()
