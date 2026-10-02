"""Usuarios y roles (RBAC)."""
from __future__ import annotations

import streamlit as st

from models.domain import Role
from security.rbac import P, ROLE_PERMISSIONS
from ui.components import demo_banner, header
from ui.state import cid, container, guard, run_safely, tr


def render() -> None:
    user = guard("users.manage")
    c = container()
    header(tr("nav.users"), "Altas, roles, bloqueo y restablecimiento con contraseñas temporales.")
    demo_banner()
    rows = c.users.list(user)
    st.dataframe(rows, hide_index=True)

    st.markdown("### Crear usuario")
    with st.form("new-user"):
        a, b, d = st.columns(3)
        username = a.text_input("Usuario", max_chars=40)
        display = b.text_input("Nombre visible", max_chars=120)
        role = d.selectbox("Rol", Role.values())
        if st.form_submit_button("Crear"):
            temp = run_safely(lambda: c.users.create(user, username, display, role, cid()))
            if temp:
                st.success("Usuario creado. Entrega esta contraseña temporal por un canal seguro; se pedirá cambiarla:")
                st.code(temp, language=None)

    if not rows:
        return
    st.markdown("### Gestionar usuario")
    options = {f"{r['username']} · {r['role']}": r for r in rows}
    target = options[st.selectbox("Usuario", list(options))]
    a, b = st.columns(2)
    with a.form("role-change"):
        new_role = st.selectbox("Nuevo rol", Role.values(), index=Role.values().index(target["role"]))
        reason = st.text_input("Motivo (obligatorio)")
        if st.form_submit_button("Cambiar rol"):
            if run_safely(lambda: c.users.change_role(user, target["id"], new_role, reason, cid()) or True,
                          "Rol actualizado."):
                st.rerun()
    with b:
        if st.button("Restablecer contraseña"):
            temp = run_safely(lambda: c.users.reset_password(user, target["id"], cid()))
            if temp:
                st.code(temp, language=None)
                st.caption("Contraseña temporal: se exigirá cambio al iniciar sesión.")
        if st.button("Desbloquear"):
            run_safely(lambda: c.users.unlock(user, target["id"], cid()), "Cuenta desbloqueada.")
        label = "Desactivar" if target["is_active"] else "Activar"
        if st.button(label):
            if run_safely(lambda: c.users.set_active(user, target["id"], not target["is_active"], cid()) or True,
                          "Estado actualizado."):
                st.rerun()

    st.markdown("### Matriz RBAC")
    roles = Role.values()
    matrix = [{"Permiso": perm, "Descripción": desc, **{r: ("✔" if perm in ROLE_PERMISSIONS[r] else "") for r in roles}}
              for perm, desc in P.items()]
    st.dataframe(matrix, hide_index=True)
    st.caption("Active Directory: integración futura configurable (desactivada). La aplicación no depende de AD.")
