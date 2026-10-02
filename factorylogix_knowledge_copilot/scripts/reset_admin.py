"""Procedimiento de emergencia: restablece (o crea) una cuenta Administrador desde el servidor.

Requiere acceso local a la carpeta de la aplicación (control físico/lógico del servidor). Pide la nueva
contraseña de forma oculta, la valida contra la política y registra el evento en auditoría.
Uso: .venv\\Scripts\\python.exe scripts\\reset_admin.py [usuario]
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.errors import ValidationError  # noqa: E402
from services.container import build_container  # noqa: E402
from security.passwords import hash_password, validate_password_policy  # noqa: E402


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    container = build_container(bootstrap=False)
    password = getpass.getpass(f"Nueva contraseña para '{username}': ")
    confirm = getpass.getpass("Confirmar contraseña: ")
    if password != confirm:
        print("Las contraseñas no coinciden.")
        return 1
    try:
        validate_password_policy(password, username, int(container.settings.get("security.password_min_length", 12)))
    except ValidationError as exc:
        print(exc.user_message)
        return 1
    users = container.auth.users
    row = users.get_by_username(username)
    if row is None:
        users.create(username=username, display_name="Administrador (recuperación)", role="Administrator",
                     password_hash=hash_password(password), must_change_password=False)
        action = "user.emergency_create_admin"
    else:
        users.update(row["id"], password_hash=hash_password(password), role="Administrator", is_active=1,
                     failed_attempts=0, locked_until=None, must_change_password=0)
        action = "user.emergency_reset_admin"
    container.audit_repo.append(username="local-console", role="Administrator", action=action, object_type="user",
                                object_id=username, result="success", reason="procedimiento de recuperación local")
    print(f"Cuenta '{username}' lista. Evento registrado en auditoría.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
