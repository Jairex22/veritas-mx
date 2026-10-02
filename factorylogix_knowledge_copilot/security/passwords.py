"""Hash de contraseñas con scrypt (stdlib). Respaldo PBKDF2-SHA256 si scrypt no está disponible."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets

from core.errors import ValidationError

_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
_PBKDF2_ITER = 600_000


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    try:
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
                                maxmem=64 * 1024 * 1024, dklen=32)
        return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"
    except (AttributeError, ValueError):
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
        return f"pbkdf2${_PBKDF2_ITER}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if parts[0] == "scrypt":
            n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
            salt, expected = base64.b64decode(parts[4]), base64.b64decode(parts[5])
            digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                                    maxmem=64 * 1024 * 1024, dklen=len(expected))
        elif parts[0] == "pbkdf2":
            iterations = int(parts[1])
            salt, expected = base64.b64decode(parts[2]), base64.b64decode(parts[3])
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        else:
            return False
        return hmac.compare_digest(digest, expected)
    except (ValueError, IndexError):
        return False


# Hash ficticio para igualar el tiempo de respuesta cuando el usuario no existe (anti-enumeración).
DUMMY_HASH = hash_password(secrets.token_hex(16))

_COMMON = {"password", "contrasena", "123456789012", "factorylogix", "administrator", "admin12345678",
           "qwertyuiop12", "bienvenido123", "welcome12345"}


def validate_password_policy(password: str, username: str = "", min_length: int = 12) -> None:
    problems = []
    if len(password) < min_length:
        problems.append(f"mínimo {min_length} caracteres")
    if not re.search(r"[A-Z]", password):
        problems.append("una mayúscula")
    if not re.search(r"[a-z]", password):
        problems.append("una minúscula")
    if not re.search(r"[0-9]", password):
        problems.append("un número")
    if password.lower() in _COMMON:
        problems.append("no usar contraseñas comunes")
    if username and username.lower() in password.lower():
        problems.append("no incluir el nombre de usuario")
    if problems:
        raise ValidationError("La contraseña debe tener: " + ", ".join(problems) + ".")
