"""FactoryLogix Knowledge Copilot - punto de entrada Streamlit.

Ejecutar con: streamlit run app.py  (o INICIAR_WINDOWS.bat)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from streamlit import runtime as _st_runtime

    if not _st_runtime.exists():
        # Ejecutado como "python app.py": Streamlit necesita su servidor. Se delega al lanzador oficial
        # (puerto libre, navegador, PID) en lugar de mostrar avisos "missing ScriptRunContext".
        import subprocess

        print("Iniciando FactoryLogix Knowledge Copilot mediante scripts/launch.py ...")
        sys.exit(subprocess.call([sys.executable, str(ROOT / "scripts" / "launch.py"), *sys.argv[1:]], cwd=str(ROOT)))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="FactoryLogix Knowledge Copilot", page_icon="🏭", layout="wide",
                   initial_sidebar_state="expanded")

from pages import (analytics, audit, catalog, chat, evaluations, feedback_review, governance, health,  # noqa: E402
                   incidents, settings, sources, training_center, users)
from ui.auth_view import enforce_session, logout, render_change_password, render_login  # noqa: E402
from ui.state import container, current_user, tr  # noqa: E402
from ui.theme import apply_theme  # noqa: E402

PAGES = [
    # (sección, módulo, clave de título, icono, permiso)
    ("nav.section.assistant", chat, "nav.chat", ":material/chat:", "chat.query"),
    ("nav.section.assistant", sources, "nav.sources", ":material/menu_book:", "sources.view"),
    ("nav.section.assistant", incidents, "nav.incidents", ":material/report:", "incident.create"),
    ("nav.section.knowledge", training_center, "nav.training", ":material/school:",
     ("knowledge.upload", "knowledge.approve")),
    ("nav.section.knowledge", catalog, "nav.catalog", ":material/folder_open:", "governance.view"),
    ("nav.section.knowledge", governance, "nav.governance", ":material/policy:", "governance.view"),
    ("nav.section.knowledge", feedback_review, "nav.feedback", ":material/rate_review:", "feedback.review"),
    ("nav.section.operations", evaluations, "nav.evaluations", ":material/fact_check:", "eval.view"),
    ("nav.section.operations", analytics, "nav.analytics", ":material/monitoring:", "analytics.view"),
    ("nav.section.admin", audit, "nav.audit", ":material/receipt_long:", "audit.view"),
    ("nav.section.admin", users, "nav.users", ":material/group:", "users.manage"),
    ("nav.section.admin", settings, "nav.settings", ":material/settings:", "settings.manage"),
    ("nav.section.admin", health, "nav.health", ":material/health_and_safety:", "health.view"),
]


def _sidebar(user) -> None:
    c = container()
    with st.sidebar:
        logo = c.settings_service.logo_bytes()
        if logo:
            st.image(logo, width=140)
        branding = c.settings_service.branding()
        st.markdown(f"**{branding.get('product_name', '')}**")
        st.caption(f"{branding.get('site', '')} · v{c.settings.get('app.version', '')} · "
                   f"{c.settings.get('app.environment', '')}")
        st.markdown(f"👤 **{user.display_name}**  \n{user.role}")
        if st.button(tr("logout"), key="logout-btn"):
            logout("logout")
        st.caption(f"Soporte: {branding.get('support_contact', '')}")


def main() -> None:
    c = container()
    apply_theme(c.settings_service.branding())
    with st.sidebar:
        choice = st.radio("Idioma / Language", ["es", "en"], horizontal=True,
                          index=0 if st.session_state.get("lang", "es") == "es" else 1,
                          format_func=lambda v: "Español" if v == "es" else "English", key="lang_choice")
        st.session_state["lang"] = choice

    user = current_user()
    if user is None:
        st.navigation([st.Page(render_login, title=tr("login.title"), url_path="login")], position="hidden").run()
        return
    enforce_session()
    user = current_user()
    if user.must_change_password:
        st.navigation([st.Page(render_change_password, title=tr("pwd.title"), url_path="password")],
                      position="hidden").run()
        return

    _sidebar(user)
    sections: dict[str, list] = {}
    for section, module, title_key, icon, permission in PAGES:
        required = permission if isinstance(permission, tuple) else (permission,)
        if any(user.can(p) for p in required):
            sections.setdefault(tr(section), []).append(
                st.Page(module.render, title=tr(title_key), icon=icon, url_path=module.__name__.split(".")[-1],
                        default=module is chat))
    st.navigation(sections).run()


main()
