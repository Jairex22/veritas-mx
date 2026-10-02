"""Configuración: identidad visual, parámetros RAG, sentimiento, LLM local y vista segura de configuración."""
from __future__ import annotations

import streamlit as st

from sentiment.analyzer import PURPOSE_ES
from ui.components import demo_banner, header
from ui.state import cid, container, guard, run_safely, tr


def render() -> None:
    user = guard("settings.manage")
    c = container()
    header(tr("nav.settings"), "Cambios auditados. Los secretos solo se configuran en variables de entorno (.env).")
    demo_banner()
    tabs = st.tabs(["Identidad visual", "Parámetros", "LLM local", "Vista de configuración"])
    with tabs[0]:
        branding = c.settings_service.branding()
        with st.form("branding"):
            a, b = st.columns(2)
            values = {
                "product_name": a.text_input("Nombre del producto", branding.get("product_name", "")),
                "company_name": b.text_input("Empresa", branding.get("company_name", "")),
                "site": a.text_input("Sitio / planta", branding.get("site", "")),
                "support_contact": b.text_input("Información de soporte", branding.get("support_contact", "")),
                "primary_color": a.color_picker("Color primario", branding.get("primary_color", "#0B5CAD")),
                "accent_color": b.color_picker("Color de acento", branding.get("accent_color", "#F2A900")),
            }
            if st.form_submit_button(tr("common.save")):
                run_safely(lambda: c.settings_service.update_branding(user, values, cid()), "Identidad actualizada.")
        logo = st.file_uploader("Logo (PNG/JPG, máx. 2 MB)", type=["png", "jpg", "jpeg"])
        if logo and st.button("Guardar logo"):
            run_safely(lambda: c.settings_service.upload_logo(user, logo.name, logo.getvalue(), cid()), "Logo guardado.")
    with tabs[1]:
        st.caption(PURPOSE_ES)
        with st.form("runtime"):
            sentiment = st.checkbox("Análisis de sentimiento habilitado", bool(c.settings.get("sentiment.enabled")))
            retention = st.number_input("Retención de etiqueta de sentimiento (días)", 1, 365,
                                        int(c.settings.get("sentiment.retention_days", 30)))
            min_rel = st.slider("Relevancia mínima para responder", 0.2, 0.9,
                                float(c.settings.get("rag.min_relevance", 0.4)), 0.01)
            top_k = st.number_input("Fragmentos recuperados (top-k)", 1, 12, int(c.settings.get("rag.top_k", 6)))
            four_eyes = st.checkbox("Segregación de funciones (quien carga no aprueba)",
                                    bool(c.settings.get("governance.require_four_eyes", True)))
            idle = st.number_input("Expiración de sesión por inactividad (min)", 5, 480,
                                   int(c.settings.get("security.session_idle_minutes", 30)))
            env = st.selectbox("Entorno", ["DEMO", "PILOT", "PRODUCTION"],
                               index=["DEMO", "PILOT", "PRODUCTION"].index(str(c.settings.get("app.environment"))
                                                                           .upper()))
            if st.form_submit_button(tr("common.save")):
                updates = {"sentiment.enabled": sentiment, "sentiment.retention_days": retention,
                           "rag.min_relevance": min_rel, "rag.top_k": top_k,
                           "governance.require_four_eyes": four_eyes, "security.session_idle_minutes": idle,
                           "app.environment": env}
                ok = True
                for key, value in updates.items():
                    ok = run_safely(lambda k=key, v=value: c.settings_service.update_runtime(user, k, v, cid())
                                    or True) and ok
                if ok:
                    c.apply_runtime()
                    st.success("Parámetros guardados y aplicados.")
    with tabs[2]:
        st.caption("Opcional. Solo hosts locales o de red privada. Sin LLM, la app usa el modo extractivo seguro.")
        with st.form("llm"):
            provider = st.selectbox("Proveedor", ["none", "ollama", "llamacpp"],
                                    index=["none", "ollama", "llamacpp"].index(c.settings.get("llm.provider", "none")))
            base_url = st.text_input("URL base", c.settings.get("llm.base_url", "http://127.0.0.1:11434"))
            model = st.text_input("Modelo (Ollama)", c.settings.get("llm.model", ""))
            if st.form_submit_button(tr("common.save")):
                ok = all(run_safely(lambda k=k, v=v: c.settings_service.update_runtime(user, k, v, cid()) or True)
                         for k, v in (("llm.base_url", base_url), ("llm.model", model), ("llm.provider", provider)))
                if ok:
                    c.apply_runtime()
                    st.success("Configuración de LLM aplicada.")
        status = c.engine.llm.available()
        st.info(f"Estado del LLM: {c.engine.llm.name} → {'disponible' if status else 'no disponible (modo extractivo)'}")
    with tabs[3]:
        safe = {k: c.settings.get(k) for k in ("app", "server", "security", "ingestion", "rag", "governance",
                                               "access_matrix", "escalation")}
        odata = dict(c.settings.get("connectors.odata", {}) or {})
        safe["connectors.odata"] = odata
        safe["secrets_configured"] = sorted(c.settings.secrets.keys())
        st.json(safe)
        st.caption("Los valores de secretos nunca se muestran. Para habilitar OData ver docs/GUIA_ODATA_SEGURO.md.")
