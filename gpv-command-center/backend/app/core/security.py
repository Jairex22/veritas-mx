"""Autenticación, sesiones, roles, permisos y CSRF."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

from .db import Database
from .errors import Forbidden, NotAvailable, Unauthorized


class Role(str, Enum):
    OPERATOR = "operator"
    ENGINEERING = "engineering"
    QUALITY = "quality"
    ADMIN = "admin"


ROLE_LABELS = {
    Role.OPERATOR: "Operador",
    Role.ENGINEERING: "Ingeniería",
    Role.QUALITY: "Calidad",
    Role.ADMIN: "Administrador autorizado",
}

# Permisos por rol. Lectura para todos; acciones según responsabilidad.
PERMISSIONS: dict[str, set[Role]] = {
    "trace.read": {Role.OPERATOR, Role.ENGINEERING, Role.QUALITY, Role.ADMIN},
    "diagnostics.read": {Role.OPERATOR, Role.ENGINEERING, Role.QUALITY, Role.ADMIN},
    "metrics.read": {Role.OPERATOR, Role.ENGINEERING, Role.QUALITY, Role.ADMIN},
    "operations.read": {Role.OPERATOR, Role.ENGINEERING, Role.QUALITY, Role.ADMIN},
    "packing.use": {Role.OPERATOR, Role.QUALITY, Role.ADMIN},
    "labels.print": {Role.OPERATOR, Role.QUALITY, Role.ADMIN},
    "labels.reprint": {Role.QUALITY, Role.ADMIN},
    "audit.read": {Role.ENGINEERING, Role.QUALITY, Role.ADMIN},
    "connectors.read": {Role.ENGINEERING, Role.QUALITY, Role.ADMIN},
    "connectors.probe": {Role.ENGINEERING, Role.ADMIN},
    "odata.explore": {Role.ENGINEERING, Role.QUALITY, Role.ADMIN},
    "connectors.configure": {Role.ADMIN},
    "demo.reset": {Role.ADMIN},
}


def has_permission(role: Role, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())


@dataclass(frozen=True)
class SessionUser:
    username: str
    display_name: str
    role: Role
    provider: str
    csrf_token: str
    expires_at: str

    def require(self, permission: str) -> None:
        if not has_permission(self.role, permission):
            raise Forbidden(
                f"El rol '{ROLE_LABELS[self.role]}' no tiene el permiso '{permission}'.",
                details={"permission": permission, "role": self.role.value},
            )

    def public(self) -> dict:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role.value,
            "role_label": ROLE_LABELS[self.role],
            "provider": self.provider,
            "expires_at": self.expires_at,
            "permissions": sorted(p for p in PERMISSIONS if has_permission(self.role, p)),
        }


# Usuarios de demostración: sin contraseña, sólo existen en modo DEMO.
DEMO_USERS = {
    "demo.operador": ("Operador DEMO", Role.OPERATOR),
    "demo.ingenieria": ("Ingeniería DEMO", Role.ENGINEERING),
    "demo.calidad": ("Calidad DEMO", Role.QUALITY),
    "demo.admin": ("Administrador DEMO", Role.ADMIN),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class SessionStore:
    def __init__(self, db: Database, ttl_minutes: int):
        self.db = db
        self.ttl = timedelta(minutes=ttl_minutes)

    def create(self, username: str, display_name: str, role: Role, provider: str) -> tuple[str, SessionUser]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = _now()
        expires = now + self.ttl
        self.db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
            (_hash_token(token), username, display_name, role.value, provider, csrf,
             now.isoformat(), expires.isoformat(), now.isoformat()),
        )
        return token, SessionUser(username, display_name, role, provider, csrf, expires.isoformat())

    def get(self, token: str | None) -> SessionUser | None:
        if not token:
            return None
        rows = self.db.query("SELECT * FROM sessions WHERE token_hash=?", (_hash_token(token),))
        if not rows:
            return None
        row = rows[0]
        if datetime.fromisoformat(row["expires_at"]) < _now():
            self.revoke(token)
            return None
        self.db.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (_now().isoformat(), row["token_hash"]))
        return SessionUser(row["username"], row["display_name"], Role(row["role"]), row["provider"],
                           row["csrf_token"], row["expires_at"])

    def revoke(self, token: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_hash_token(token),))

    def purge_expired(self) -> None:
        self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))


def verify_csrf(user: SessionUser, header_value: str | None) -> None:
    if not header_value or not hmac.compare_digest(user.csrf_token, header_value):
        raise Forbidden("Token CSRF ausente o inválido.", code="CSRF_FAILED")


class AuthProviders:
    """Proveedores de autenticación disponibles.

    - demo: sólo en modo DEMO, claramente identificado.
    - corporate: Autenticación Integrada de Windows delegada a un proxy inverso
      de confianza (IIS). El proxy autentica al usuario y envía su identidad en
      un encabezado; sólo se acepta desde IPs de proxy configuradas y el rol se
      asigna exclusivamente por el archivo de mapeo `user_roles.json`.
      OIDC / Entra ID queda para una fase posterior.
    """

    def __init__(self, demo_enabled: bool, proxy_header: str = "", trusted_ips: tuple[str, ...] = (),
                 roles_file: Path | None = None):
        self.demo_enabled = demo_enabled
        self.proxy_header = proxy_header
        self.trusted_ips = set(trusted_ips)
        self.roles_file = roles_file

    @property
    def corporate_enabled(self) -> bool:
        return bool(self.proxy_header)

    def describe(self) -> list[dict]:
        return [
            {
                "id": "demo",
                "label": "Acceso de demostración (DEMO)",
                "available": self.demo_enabled,
                "reason": None if self.demo_enabled else "Deshabilitado: el acceso DEMO sólo existe en modo DEMO.",
                "users": [{"username": u, "display_name": d, "role": r.value, "role_label": ROLE_LABELS[r]}
                          for u, (d, r) in DEMO_USERS.items()] if self.demo_enabled else [],
            },
            {
                "id": "corporate",
                "label": "Cuenta corporativa de Windows",
                "available": self.corporate_enabled,
                "reason": None if self.corporate_enabled else
                "NO DISPONIBLE: requiere publicar el servicio detrás de IIS con Autenticación de Windows "
                "(GPV_PROXY_AUTH_HEADER) y el archivo de roles aprobado. OIDC/Entra ID pendiente para fase 2.",
                "users": [],
            },
        ]

    def authenticate_demo(self, username: str) -> tuple[str, Role]:
        if not self.demo_enabled:
            raise NotAvailable("El acceso DEMO está deshabilitado en este modo.", code="DEMO_LOGIN_DISABLED")
        if username not in DEMO_USERS:
            raise Unauthorized("Usuario DEMO desconocido.")
        display, role = DEMO_USERS[username]
        return display, role

    def _roles(self) -> dict[str, str]:
        if not self.roles_file or not self.roles_file.is_file():
            return {}
        data = json.loads(self.roles_file.read_text(encoding="utf-8"))
        users = data.get("users", data) if isinstance(data, dict) else {}
        return {str(k).lower(): str(v) for k, v in users.items() if not str(k).startswith("_")}

    def authenticate_corporate(self, client_ip: str | None, header_value: str | None) -> tuple[str, str, Role]:
        if not self.corporate_enabled:
            raise NotAvailable("Autenticación corporativa no configurada.", code="CORPORATE_AUTH_NOT_AVAILABLE")
        if client_ip not in self.trusted_ips:
            raise Unauthorized("La identidad corporativa sólo se acepta a través del proxy autorizado.",
                               code="UNTRUSTED_PROXY")
        username = (header_value or "").strip()
        if not username or len(username) > 128:
            raise Unauthorized("El proxy no envió una identidad de Windows.", code="NO_PROXY_IDENTITY")
        role_name = self._roles().get(username.lower())
        if role_name not in {r.value for r in Role}:
            raise Forbidden(f"El usuario '{username}' no tiene un rol asignado en el Command Center.",
                            code="USER_NOT_AUTHORIZED")
        return username, username.split("\\")[-1], Role(role_name)
