"""Administración de usuarios y roles, creación segura del administrador inicial y usuarios DEMO."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import Settings
from core.errors import NotFound, ValidationError
from core.utils import generate_password
from models.domain import AuthenticatedUser, Role
from repositories.users import UserRepository
from schemas.validation import validate_role, validate_username
from security.passwords import hash_password
from security.rbac import require
from security.sanitize import clean_user_text
from services.audit_helper import Auditor

FIRST_RUN_FILE = "PRIMER_ACCESO_ADMIN.txt"
DEMO_USERS_FILE = "USUARIOS_DEMO.txt"


class UserService:
    def __init__(self, settings: Settings, users: UserRepository, audit: Auditor):
        self.settings = settings
        self.users = users
        self.audit = audit
        self.data_dir = settings.path("paths.data_dir")

    def list(self, user: AuthenticatedUser) -> list[dict[str, Any]]:
        require(user, "users.manage")
        return self.users.list_all()

    def create(self, actor: AuthenticatedUser, username: str, display_name: str, role: str,
               correlation_id: str = "") -> str:
        """Crea un usuario con contraseña temporal aleatoria (debe cambiarla al primer acceso)."""
        require(actor, "users.manage")
        username = validate_username(username)
        role = validate_role(role)
        display_name = clean_user_text(display_name, 120) or username
        if self.users.get_by_username(username):
            raise ValidationError("El usuario ya existe.")
        temp = generate_password()
        uid = self.users.create(username=username, display_name=display_name, role=role,
                                password_hash=hash_password(temp), must_change_password=True)
        self.audit(actor, "user.create", "user", uid, "success", details=f"role={role}", correlation_id=correlation_id)
        return temp

    def change_role(self, actor: AuthenticatedUser, user_id: str, role: str, reason: str,
                    correlation_id: str = "") -> None:
        require(actor, "users.manage")
        role = validate_role(role)
        reason = clean_user_text(reason, 300)
        if not reason:
            raise ValidationError("Indica el motivo del cambio de rol.")
        target = self.users.get(user_id)
        if not target:
            raise NotFound("Usuario no encontrado.")
        if target["role"] == Role.ADMINISTRATOR.value and role != Role.ADMINISTRATOR.value \
                and self.users.count_active_admins() <= 1:
            raise ValidationError("No se puede quitar el rol al último administrador activo.")
        self.users.update(user_id, role=role)
        self.audit(actor, "user.role_change", "user", user_id, "success", reason=reason,
                   details=f"{target['role']} -> {role}", correlation_id=correlation_id)

    def set_active(self, actor: AuthenticatedUser, user_id: str, active: bool, correlation_id: str = "") -> None:
        require(actor, "users.manage")
        target = self.users.get(user_id)
        if not target:
            raise NotFound("Usuario no encontrado.")
        if target["id"] == actor.id and not active:
            raise ValidationError("No puedes desactivar tu propia cuenta.")
        if not active and target["role"] == Role.ADMINISTRATOR.value and self.users.count_active_admins() <= 1:
            raise ValidationError("No se puede desactivar al último administrador activo.")
        self.users.update(user_id, is_active=int(active))
        self.audit(actor, "user.activate" if active else "user.deactivate", "user", user_id, "success",
                   correlation_id=correlation_id)

    def reset_password(self, actor: AuthenticatedUser, user_id: str, correlation_id: str = "") -> str:
        require(actor, "users.manage")
        if not self.users.get(user_id):
            raise NotFound("Usuario no encontrado.")
        temp = generate_password()
        self.users.update(user_id, password_hash=hash_password(temp), must_change_password=1, failed_attempts=0,
                          locked_until=None)
        self.audit(actor, "user.reset_password", "user", user_id, "success", correlation_id=correlation_id)
        return temp

    def unlock(self, actor: AuthenticatedUser, user_id: str, correlation_id: str = "") -> None:
        require(actor, "users.manage")
        self.users.update(user_id, failed_attempts=0, locked_until=None)
        self.audit(actor, "user.unlock", "user", user_id, "success", correlation_id=correlation_id)

    # --- arranque seguro ---
    def ensure_initial_admin(self) -> str | None:
        """Si no existe ningún usuario, crea 'admin' con contraseña aleatoria de un solo uso.

        La contraseña se muestra en consola y se guarda en data/PRIMER_ACCESO_ADMIN.txt (local, fuera del
        ZIP). Se exige cambio al primer acceso y el archivo se elimina al cambiarla."""
        if self.users.count() > 0:
            return None
        password = generate_password(18)
        self.users.create(username="admin", display_name="Administrador inicial", role=Role.ADMINISTRATOR.value,
                          password_hash=hash_password(password), must_change_password=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / FIRST_RUN_FILE).write_text(
            "FactoryLogix Knowledge Copilot - acceso inicial\n"
            "Usuario: admin\n"
            f"Contraseña temporal (un solo uso): {password}\n"
            "Se exigirá cambiarla al iniciar sesión. Este archivo se elimina automáticamente después del cambio.\n",
            encoding="utf-8")
        self.audit.repo.append(username="system", role="Administrator", action="user.bootstrap_admin",
                               object_type="user", object_id="admin", result="success")
        return password

    def first_run_file(self) -> Path:
        return self.data_dir / FIRST_RUN_FILE

    def clear_first_run_file(self) -> None:
        path = self.first_run_file()
        if path.is_file():
            path.unlink()

    def ensure_demo_users(self) -> dict[str, str]:
        """Crea un usuario DEMO por rol (si no existen) con contraseñas aleatorias guardadas localmente."""
        created: dict[str, str] = {}
        for role in Role:
            username = "demo_" + role.value.lower().replace(" ", "_")
            if self.users.get_by_username(username):
                continue
            password = generate_password(14)
            self.users.create(username=username, display_name=f"DEMO {role.value}", role=role.value,
                              password_hash=hash_password(password), must_change_password=False, is_demo=True)
            created[username] = password
        if created:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            lines = ["USUARIOS DEMO (solo para demostración; desactivar en piloto/producción)", ""]
            lines += [f"{u}\t{p}" for u, p in created.items()]
            path = self.data_dir / DEMO_USERS_FILE
            existing = path.read_text(encoding="utf-8") + "\n" if path.is_file() else ""
            path.write_text(existing + "\n".join(lines) + "\n", encoding="utf-8")
            self.audit.repo.append(username="system", role="Administrator", action="user.create_demo_users",
                                   object_type="user", object_id="demo_*", result="success",
                                   details=f"count={len(created)}")
        return created
