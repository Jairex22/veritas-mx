"""Detiene el servidor iniciado por INICIAR_WINDOWS.bat (usado por DETENER_WINDOWS.bat)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_settings  # noqa: E402
from scripts.process_utils import read_pid_file, remove_pid_file, stop_process  # noqa: E402


def main() -> int:
    settings = load_settings()
    pid_file = settings.path("paths.data_dir") / "server.pid"
    info = read_pid_file(pid_file)
    if not info:
        print("No hay un servidor registrado en ejecución.")
        return 0
    if stop_process(info["pid"]):
        print(f"Servidor detenido (PID {info['pid']}, puerto {info['port']}).")
    else:
        print("El proceso registrado ya no estaba en ejecución.")
    remove_pid_file(pid_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
