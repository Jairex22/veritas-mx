"""Obtención de credenciales sin almacenarlas en código, config ni SQLite.

Fuentes soportadas:
- env: variables de entorno GPV_ODATA_USER / GPV_ODATA_PASSWORD (sesión de usuario).
- windows_credential_manager: credencial genérica del Administrador de
  credenciales de Windows (por usuario, sin permisos de administrador), leída
  con ctypes/advapi32 (biblioteca estándar).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

ENV_USER = "GPV_ODATA_USER"
ENV_PASSWORD = "GPV_ODATA_PASSWORD"


@dataclass(frozen=True)
class Credential:
    username: str
    password: str

    def __repr__(self) -> str:  # nunca exponer la contraseña en logs/trazas
        return f"Credential(username={self.username!r}, password='***')"


class CredentialError(RuntimeError):
    pass


def from_env() -> Credential | None:
    user = os.environ.get(ENV_USER, "").strip()
    pwd = os.environ.get(ENV_PASSWORD, "")
    if user and pwd:
        return Credential(user, pwd)
    return None


def _wincred_structs():
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]
    return ctypes, wintypes, CREDENTIAL


def from_windows_credential_manager(target: str) -> Credential | None:
    if sys.platform != "win32":
        raise CredentialError("El Administrador de credenciales solo está disponible en Windows")
    ctypes, wintypes, CREDENTIAL = _wincred_structs()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    pcred = ctypes.POINTER(CREDENTIAL)()
    CRED_TYPE_GENERIC = 1
    if not advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        return None
    try:
        cred = pcred.contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
        password = blob.decode("utf-16-le")
        return Credential(cred.UserName or "", password)
    finally:
        advapi32.CredFree(pcred)


def save_to_windows_credential_manager(target: str, username: str, password: str) -> None:
    if sys.platform != "win32":
        raise CredentialError("El Administrador de credenciales solo está disponible en Windows")
    ctypes, wintypes, CREDENTIAL = _wincred_structs()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    blob = password.encode("utf-16-le")
    buf = (ctypes.c_byte * len(blob)).from_buffer_copy(blob)
    cred = CREDENTIAL()
    cred.Type = 1                 # CRED_TYPE_GENERIC
    cred.TargetName = target
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))
    cred.Persist = 2              # CRED_PERSIST_LOCAL_MACHINE (solo este usuario)
    cred.UserName = username
    if not advapi32.CredWriteW(ctypes.byref(cred), 0):
        raise CredentialError(f"CredWriteW falló (código {ctypes.get_last_error()})")


def get_credential(odata_cfg: dict) -> Credential | None:
    source = odata_cfg.get("credential_source", "env")
    if source == "env":
        return from_env()
    if source == "windows_credential_manager":
        return from_windows_credential_manager(odata_cfg.get("credential_target", ""))
    raise CredentialError(f"Fuente de credenciales no soportada: {source}")


def credential_configured(odata_cfg: dict) -> bool:
    try:
        return get_credential(odata_cfg) is not None
    except CredentialError:
        return False
