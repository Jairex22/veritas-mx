"""
Autenticación y control de acceso.

- Contraseñas: hash con bcrypt (passlib). Nunca se guardan en texto plano.
- Sesión: JWT firmado con `JWT_SECRET` (variable de entorno, nunca hardcodeado).
- Bloqueo temporal: tras `LOGIN_MAX_ATTEMPTS` fallos consecutivos, la cuenta se
  bloquea `LOGIN_LOCKOUT_MINUTES` minutos.
- RBAC: dependencias `require_role(...)` para proteger rutas por rol.
- Preparado para Active Directory: `User.external_directory_id` queda listo
  para mapear contra un directorio externo sin cambiar el resto del sistema
  (ver MANUAL_FACTORYLOGIX.md / README, sección "Integración futura con AD").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User, UserRole

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "role": user.role.value,
        "display_name": user.display_name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión no es válida o expiró. Inicia sesión nuevamente.",
        ) from exc


def is_locked(user: User) -> bool:
    return bool(user.locked_until and user.locked_until > datetime.utcnow())


def register_failed_attempt(user: User, db: Session) -> None:
    user.failed_attempts += 1
    if user.failed_attempts >= settings.login_max_attempts:
        user.locked_until = datetime.utcnow() + timedelta(minutes=settings.login_lockout_minutes)
        user.failed_attempts = 0
    db.add(user)
    db.commit()


def register_successful_login(user: User, db: Session) -> None:
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    db.add(user)
    db.commit()


class CurrentUser:
    def __init__(self, username: str, role: str, display_name: str):
        self.username = username
        self.role = role
        self.display_name = display_name


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inicia sesión para continuar.",
        )
    payload = decode_access_token(credentials.credentials)
    return CurrentUser(
        username=payload["sub"], role=payload["role"], display_name=payload.get("display_name", "")
    )


def require_role(*allowed_roles: UserRole):
    allowed_values = {role.value for role in allowed_roles}

    def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no tiene permiso para esta acción.",
            )
        return current_user

    return _dependency


# Cualquier usuario autenticado (todas las pantallas de consulta).
require_authenticated = get_current_user
# Sólo roles que pueden modificar configuración / datos maestros.
require_admin_or_engineer = require_role(UserRole.ADMIN, UserRole.ING_MES)
# Roles que pueden registrar acciones de capacitación y notas de supervisor.
require_supervisor_or_above = require_role(UserRole.ADMIN, UserRole.ING_MES, UserRole.SUPERVISOR, UserRole.LIDER_LINEA)
