"""Autenticación local: hash seguro, bloqueo por intentos, anti-enumeración y sesiones con expiración.

Active Directory: ver `ActiveDirectoryConfig`. Está desactivado por defecto y la aplicación nunca
depende de AD para arrancar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.errors import AccountLocked, AuthenticationError, RateLimitExceeded, ValidationError
from core.logging_setup import get_logger
from core.utils import now_iso, parse_dt, utcnow
from models.domain import AuthenticatedUser
from repositories.audit import AuditRepository
from repositories.users import UserRepository
from security.passwords import DUMMY_HASH, hash_password, validate_password_policy, verify_password
from security.rate_limit import RateLimiter
from security.rbac import AccessPolicy

log = get_logger("auth")


@dataclass(frozen=True)
class ActiveDirectoryConfig:
    """Configuración futura de AD/LDAP (no implementa conexión: requiere validación de TI)."""

    enabled: bool = False
    server: str = ""
    base_dn: str = ""
    group_role_map: tuple[tuple[str, str], ...] = ()


class AuthService:
    def __init__(self, users: UserRepository, audit: AuditRepository, policy: AccessPolicy, *,
                 max_failed: int = 5, lockout_minutes: int = 15, login_rate_per_minute: int = 10,
                 password_min_length: int = 12, idle_minutes: int = 30):
        self.users = users
        self.audit = audit
        self.policy = policy
        self.max_failed = max_failed
        self.lockout = timedelta(minutes=lockout_minutes)
        self.password_min_length = password_min_length
        self.idle = timedelta(minutes=idle_minutes)
        self.limiter = RateLimiter(login_rate_per_minute, 60)

    def build_user(self, row: dict) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=row["id"], username=row["username"], display_name=row["display_name"], role=row["role"],
            permissions=self.policy.permissions_for(row["role"]), clearance=self.policy.clearance_for(row["role"]),
            must_change_password=bool(row["must_change_password"]), language=row.get("preferred_language", "es"),
        )

    def authenticate(self, username: str, password: str, correlation_id: str = "") -> AuthenticatedUser:
        username = (username or "").strip()[:80]
        if not username or not password:
            raise AuthenticationError()
        if not self.limiter.allow(username.lower()):
            self.audit.append(username=username, role="-", action="auth.login", object_type="user",
                              object_id=username, result="denied", reason="rate limit",
                              correlation_id=correlation_id)
            raise RateLimitExceeded()

        row = self.users.get_by_username(username)
        if row is None:
            verify_password(password, DUMMY_HASH)  # igualar tiempos: evita enumeración de usuarios
            self.audit.append(username=username, role="-", action="auth.login", object_type="user",
                              object_id=username, result="failure", reason="invalid credentials",
                              correlation_id=correlation_id)
            raise AuthenticationError()

        locked_until = parse_dt(row.get("locked_until"))
        if locked_until and locked_until > utcnow():
            verify_password(password, DUMMY_HASH)
            self.audit.append(username=row["username"], role=row["role"], action="auth.login", object_type="user",
                              object_id=row["id"], result="denied", reason="account locked",
                              correlation_id=correlation_id)
            raise AccountLocked()

        if not row["is_active"] or not verify_password(password, row["password_hash"]):
            attempts = int(row["failed_attempts"]) + 1
            fields: dict = {"failed_attempts": attempts}
            reason = "invalid credentials" if row["is_active"] else "inactive account"
            if attempts >= self.max_failed:
                fields["locked_until"] = (utcnow() + self.lockout).replace(microsecond=0).isoformat()
                fields["failed_attempts"] = 0
                reason += "; account locked"
            self.users.update(row["id"], **fields)
            self.audit.append(username=row["username"], role=row["role"], action="auth.login", object_type="user",
                              object_id=row["id"], result="failure", reason=reason, correlation_id=correlation_id)
            raise AuthenticationError()

        self.users.update(row["id"], failed_attempts=0, locked_until=None, last_login_at=now_iso())
        self.audit.append(username=row["username"], role=row["role"], action="auth.login", object_type="user",
                          object_id=row["id"], result="success", correlation_id=correlation_id)
        log.info("login ok user_id=%s", row["id"])
        return self.build_user(row)

    def start_session(self, user: AuthenticatedUser) -> str:
        return self.users.start_session(user.id)

    def logout(self, user: AuthenticatedUser, session_id: str, reason: str = "logout",
               correlation_id: str = "") -> None:
        if session_id:
            self.users.end_session(session_id, reason)
        self.audit.append(username=user.username, role=user.role, action="auth.logout", object_type="session",
                          object_id=session_id or "-", result="success", reason=reason,
                          correlation_id=correlation_id)

    def is_idle_expired(self, last_activity: datetime | None, now: datetime | None = None) -> bool:
        if last_activity is None:
            return False
        return (now or utcnow()) - last_activity > self.idle

    def refresh(self, user_id: str) -> AuthenticatedUser | None:
        """Relee el usuario (rol/estado pueden haber cambiado). None si fue desactivado."""
        row = self.users.get(user_id)
        if not row or not row["is_active"]:
            return None
        return self.build_user(row)

    def change_password(self, user: AuthenticatedUser, current: str, new: str, confirm: str,
                        correlation_id: str = "") -> None:
        if new != confirm:
            raise ValidationError("La confirmación no coincide.")
        row = self.users.get(user.id)
        if row is None or not verify_password(current or "", row["password_hash"]):
            self.audit.append(username=user.username, role=user.role, action="auth.change_password",
                              object_type="user", object_id=user.id, result="failure",
                              reason="current password invalid", correlation_id=correlation_id)
            raise AuthenticationError("La contraseña actual no es correcta.")
        if verify_password(new, row["password_hash"]):
            raise ValidationError("La nueva contraseña debe ser distinta de la actual.")
        validate_password_policy(new, user.username, self.password_min_length)
        self.users.update(user.id, password_hash=hash_password(new), must_change_password=0,
                          password_changed_at=now_iso())
        self.audit.append(username=user.username, role=user.role, action="auth.change_password",
                          object_type="user", object_id=user.id, result="success", correlation_id=correlation_id)
