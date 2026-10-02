"""Salud del sistema, errores y respaldos."""
from __future__ import annotations

import streamlit as st

from ui.components import demo_banner, header
from ui.state import cid, container, guard, run_safely, tr

_ICON = {"OK": "🟢", "WARN": "🟡", "FAIL": "🔴", "OFF": "⚪"}


def render() -> None:
    user = guard("health.view")
    c = container()
    header(tr("nav.health"), "Estado de componentes. La app funciona aunque el LLM, OCR u OData no estén disponibles.")
    demo_banner()
    checks = c.health.checks()
    st.dataframe([{"": _ICON.get(ch.status, ""), "Componente": ch.component, "Estado": ch.status,
                   "Detalle": ch.detail} for ch in checks], hide_index=True)
    st.markdown("**Entorno**")
    st.json(c.health.environment())
    st.markdown("**Errores recientes (redactados)**")
    st.dataframe(c.errors.list(100), hide_index=True)
    if user.can("settings.manage"):
        st.markdown("### Respaldos")
        if st.button("Crear respaldo ahora"):
            path = run_safely(lambda: c.backup.create(user, cid()))
            if path:
                st.success(f"Respaldo creado: {path.name} (data/backups)")
                c.backup.prune()
        st.dataframe(c.backup.list(), hide_index=True)
        st.caption("Restauración: " + c.backup.restore_instructions())
