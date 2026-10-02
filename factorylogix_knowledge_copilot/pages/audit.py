"""Auditoría: solo lectura (append-only, cadena de hashes verificable)."""
from __future__ import annotations

import streamlit as st

from services.export_service import to_csv_bytes
from ui.components import demo_banner, header
from ui.state import cid, container, guard, tr


def render() -> None:
    user = guard("audit.view")
    c = container()
    header(tr("nav.audit"), "Registro inmutable de eventos de seguridad y gobierno (solo lectura).")
    demo_banner()
    ok, count, broken = c.audit_repo.verify_chain()
    if ok:
        st.success(f"Cadena de auditoría íntegra: {count} eventos verificados.")
    else:
        st.error(f"Se detectó una alteración en la cadena de auditoría (evento {broken}).")
    a, b, d, e = st.columns(4)
    action = a.text_input("Acción contiene", max_chars=60)
    username = b.text_input("Usuario", max_chars=60)
    result = d.selectbox("Resultado", ["", "success", "failure", "denied", "blocked", "flagged"])
    limit = e.number_input("Máx. registros", min_value=50, max_value=5000, value=500, step=50)
    rows = c.audit_repo.list(action=action, username=username, result=result, limit=int(limit))
    columns = ["ts", "username", "role", "action", "object_type", "object_id", "result", "reason", "correlation_id",
               "details", "id", "hash"]
    st.dataframe([{k: r[k] for k in columns} for r in rows], hide_index=True)
    if user.can("export.data") and st.button("Preparar exportación CSV"):
        c.auditor(user, "export.audit_csv", "audit_log", "filtered", "success", details=f"rows={len(rows)}",
                  correlation_id=cid())
        st.download_button(tr("common.export_csv"), data=to_csv_bytes(rows, columns), file_name="auditoria.csv")
    st.caption("El registro no puede modificarse ni eliminarse desde la interfaz; la base de datos lo bloquea "
               "mediante triggers y cada evento encadena el hash del anterior.")
