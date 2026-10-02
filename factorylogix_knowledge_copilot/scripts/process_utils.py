"""Utilidades de proceso seguras en Windows y Linux (sin PowerShell ni permisos de administrador)."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path


def write_pid_file(path: Path, pid: int, port: int, host: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": pid, "port": port, "host": host}), encoding="utf-8")


def read_pid_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"pid": int(data["pid"]), "port": int(data["port"]), "host": str(data.get("host", ""))}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remove_pid_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_process(pid: int) -> bool:
    """Detiene el proceso y sus hijos. En Windows usa taskkill (no requiere administrador para procesos propios)."""
    if not is_running(pid):
        return False
    if os.name == "nt":
        result = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True,
                                check=False)
        return result.returncode == 0
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline and is_running(pid):
        time.sleep(0.2)
    if is_running(pid):
        os.kill(pid, signal.SIGKILL)
    return True
