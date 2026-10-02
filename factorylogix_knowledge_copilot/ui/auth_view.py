"""Pantallas de inicio de sesión, cambio obligatorio de contraseña y control de inactividad."""
from __future__ import annotations

import streamlit as st

from core.utils import new_correlation_id, utcnow
from ui.state import container, current_user, run_safely, tr


def _header(branding: dict[str, str]) -> None:
    logo = container().settings_service.logo_bytes()
    if logo:
        st.image(logo, width=160)
    st.markdown(f"## {branding.get('product_name', 'FactoryLogix Knowledge Copilot')}")
    st.caption(f"{branding.get('company_name', '')} · {branding.get('site', '')}")


def render_login() -> None:
    c = container()
    branding = c.settings_service.branding()
    _, center, _ = st.columns([1, 2, 1])
    with center:
        _header(branding)
        if st.session_state.pop("expired_notice", False):
            st.warning(tr("session.expired"))
        with st.form("login", clear_on_submit=False):
            st.markdown(f"### {tr('login.title')}")
            username = st.text_input(tr("login.user"), max_chars=80, autocomplete="username")
            password = st.text_input(tr("login.password"), type="password", max_chars=200,
                                     autocomplete="current-password")
            submitted = st.form_submit_button(tr("login.submit"), type="primary")
        if submitted:
            correlation = new_correlation_id()
            user = run_safely(lambda: c.auth.authenticate(username, password, correlation))
            if user:
                st.session_state["user"] = user
                st.session_state["session_id"] = c.auth.start_session(user)
                st.session_state["last_activity"] = utcnow()
                st.session_state["lang"] = user.language
                st.rerun()
        if c.users.first_run_file().is_file():
            st.info(tr("login.first_run"))
        st.caption(f"Soporte: {branding.get('support_contact', '')}")


def render_change_password() -> None:
    c = container()
    user = current_user()
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown(f"### {tr('pwd.title')}")
        st.caption(tr("pwd.policy"))
        with st.form("change_pwd"):
            current = st.text_input(tr("pwd.current"), type="password", autocomplete="current-password")
            new = st.text_input(tr("pwd.new"), type="password", autocomplete="new-password")
            confirm = st.text_input(tr("pwd.confirm"), type="password", autocomplete="new-password")
            submitted = st.form_submit_button(tr("pwd.submit"), type="primary")
        if submitted:
            result = run_safely(lambda: c.auth.change_password(user, current, new, confirm, new_correlation_id()) or True)
            if result:
                if user.role == "Administrator":
                    c.users.clear_first_run_file()
                st.session_state["user"] = c.auth.refresh(user.id)
                st.success("Contraseña actualizada.")
                st.rerun()
        if st.button(tr("logout")):
            logout("logout")


def logout(reason: str) -> None:
    c = container()
    user = current_user()
    if user:
        c.auth.logout(user, st.session_state.get("session_id", ""), reason)
    for key in list(st.session_state.keys()):
        if key != "lang":
            del st.session_state[key]
    if reason == "idle_timeout":
        st.session_state["expired_notice"] = True
    st.rerun()


def enforce_session() -> None:
    """Expira sesiones inactivas y refresca rol/estado del usuario en cada interacción."""
    c = container()
    user = current_user()
    if user is None:
        return
    if c.auth.is_idle_expired(st.session_state.get("last_activity")):
        logout("idle_timeout")
    refreshed = c.auth.refresh(user.id)
    if refreshed is None:
        logout("account_disabled")
    st.session_state["user"] = refreshed
    st.session_state["last_activity"] = utcnow()
    session_id = st.session_state.get("session_id")
    if session_id:
        c.auth.users.touch_session(session_id)
