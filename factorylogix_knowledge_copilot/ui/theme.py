"""Tema visual industrial (claro, alto contraste, foco visible para navegación por teclado)."""
from __future__ import annotations

import re

import streamlit as st

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _color(value: str, default: str) -> str:
    return value if isinstance(value, str) and _HEX.match(value) else default


def apply_theme(branding: dict[str, str]) -> None:
    primary = _color(branding.get("primary_color", ""), "#0B5CAD")
    accent = _color(branding.get("accent_color", ""), "#F2A900")
    # CSS estático: solo se interpolan colores validados con regex (sin contenido de usuario).
    st.markdown(f"""
<style>
:root {{ --flkc-primary: {primary}; --flkc-accent: {accent}; }}
html, body, [class*="css"] {{ font-size: 16px; }}
h1, h2, h3 {{ color: #14212b; letter-spacing: .2px; }}
.flkc-header {{ border-left: 6px solid var(--flkc-primary); padding: 6px 14px; margin-bottom: 8px;
  background: #f4f7fa; border-radius: 6px; }}
.flkc-header .t {{ font-size: 1.35rem; font-weight: 700; color: #14212b; }}
.flkc-header .s {{ font-size: .9rem; color: #3d4b57; }}
.flkc-banner {{ background: #fff4ce; border: 1px solid var(--flkc-accent); color: #3b2f00; padding: 6px 12px;
  border-radius: 6px; font-size: .9rem; margin-bottom: 8px; }}
.flkc-badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: .85rem; }}
.flkc-high {{ background: #d7f5dd; color: #0f5a1f; border: 1px solid #2e8b47; }}
.flkc-medium {{ background: #fff1c2; color: #5c4400; border: 1px solid #c79a00; }}
.flkc-low {{ background: #ffd9d6; color: #7a1007; border: 1px solid #c23a2b; }}
.flkc-none {{ background: #e7ebef; color: #333; border: 1px solid #8a959e; }}
.flkc-section {{ font-weight: 700; color: var(--flkc-primary); margin-top: 6px; }}
button:focus-visible, input:focus-visible, textarea:focus-visible, [role="tab"]:focus-visible {{
  outline: 3px solid var(--flkc-accent) !important; outline-offset: 2px; }}
div.stButton > button[kind="primary"] {{ background: var(--flkc-primary); border-color: var(--flkc-primary); }}
textarea {{ font-size: 1.05rem !important; }}
</style>
""", unsafe_allow_html=True)
