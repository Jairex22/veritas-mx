"""Configuración en tiempo de ejecución (identidad visual y parámetros) con auditoría."""
from __future__ import annotations

import re
from typing import Any

from core.config import Settings
from core.errors import ValidationError
from models.domain import AuthenticatedUser
from repositories.operations import SettingsRepository
from security.file_validation import validate_image_attachment
from security.rbac import require
from security.sanitize import clean_user_text, safe_join
from services.audit_helper import Auditor

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

BRANDING_KEYS = ("product_name", "company_name", "site", "primary_color", "accent_color", "support_contact")

# Parámetros editables desde la interfaz: clave -> (tipo, validador)
RUNTIME_KEYS: dict[str, tuple[type, Any]] = {
    "sentiment.enabled": (bool, None),
    "sentiment.retention_days": (int, (1, 365)),
    "rag.min_relevance": (float, (0.2, 0.9)),
    "rag.top_k": (int, (1, 12)),
    "governance.require_four_eyes": (bool, None),
    "security.session_idle_minutes": (int, (5, 480)),
    "llm.provider": (str, {"none", "ollama", "llamacpp"}),
    "llm.base_url": (str, None),
    "llm.model": (str, None),
    "app.environment": (str, {"DEMO", "PILOT", "PRODUCTION"}),
}


class SettingsService:
    def __init__(self, settings: Settings, repo: SettingsRepository, audit: Auditor):
        self.settings = settings
        self.repo = repo
        self.audit = audit
        self.apply_overrides()

    def apply_overrides(self) -> None:
        for key, value in self.repo.all().items():
            if key.startswith("branding.") or key in RUNTIME_KEYS:
                self.settings.set(key, value)

    def branding(self) -> dict[str, str]:
        data = dict(self.settings.get("branding", {}) or {})
        return {k: str(v) for k, v in data.items()}

    def update_branding(self, user: AuthenticatedUser, values: dict[str, str], correlation_id: str = "") -> None:
        require(user, "settings.manage")
        for key, value in values.items():
            if key not in BRANDING_KEYS:
                raise ValidationError(f"Campo de identidad no permitido: {key}")
            value = clean_user_text(value, 200)
            if key.endswith("_color") and not _HEX.match(value):
                raise ValidationError("Los colores deben tener formato #RRGGBB.")
            if self.settings.get(f"branding.{key}") != value:
                self.repo.put(f"branding.{key}", value, user.username)
                self.settings.set(f"branding.{key}", value)
                self.audit(user, "settings.change", "setting", f"branding.{key}", "success",
                           correlation_id=correlation_id)

    def upload_logo(self, user: AuthenticatedUser, name: str, data: bytes, correlation_id: str = "") -> None:
        require(user, "settings.manage")
        vf = validate_image_attachment(name, data, max_mb=2)
        folder = self.settings.path("paths.data_dir") / "branding"
        folder.mkdir(parents=True, exist_ok=True)
        target = safe_join(folder, "logo" + vf.extension)
        target.write_bytes(data)
        rel = f"branding/{target.name}"
        self.repo.put("branding.logo_path", rel, user.username)
        self.settings.set("branding.logo_path", rel)
        self.audit(user, "settings.change", "setting", "branding.logo_path", "success", correlation_id=correlation_id)

    def logo_bytes(self) -> bytes | None:
        rel = self.settings.get("branding.logo_path")
        if not rel:
            return None
        try:
            path = safe_join(self.settings.path("paths.data_dir"), rel)
        except Exception:  # noqa: BLE001 - ruta inválida: no mostrar logo
            return None
        return path.read_bytes() if path.is_file() else None

    def update_runtime(self, user: AuthenticatedUser, key: str, value: Any, correlation_id: str = "") -> bool:
        require(user, "settings.manage")
        if key not in RUNTIME_KEYS:
            raise ValidationError("Parámetro no editable desde la interfaz.")
        kind, rule = RUNTIME_KEYS[key]
        try:
            value = kind(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Valor inválido para {key}.") from exc
        if isinstance(rule, set) and value not in rule:
            raise ValidationError(f"Valor no permitido para {key}.")
        if isinstance(rule, tuple) and not (rule[0] <= value <= rule[1]):
            raise ValidationError(f"{key} debe estar entre {rule[0]} y {rule[1]}.")
        if isinstance(value, str):
            value = clean_user_text(value, 200)
        old = self.settings.get(key)
        if old == value:
            return False
        self.repo.put(key, value, user.username)
        self.settings.set(key, value)
        self.audit(user, "settings.change", "setting", key, "success", details=f"{old} -> {value}",
                   correlation_id=correlation_id)
        return True
