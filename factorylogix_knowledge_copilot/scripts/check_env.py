"""Verificaciones usadas por los scripts BAT.

  python scripts/check_env.py python          -> valida versión de Python (exit 0 ok, 2 no soportada)
  python scripts/check_env.py installed       -> exit 0 si dependencias instaladas y requirements sin cambios
  python scripts/check_env.py mark-installed  -> registra la huella de requirements.txt tras instalar
"""
from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".venv" / ".flkc_requirements.sha256"
MIN_VERSION = (3, 10)
MAX_TESTED = (3, 13)
REQUIRED_MODULES = ["streamlit", "numpy", "pandas", "pypdf", "docx", "openpyxl", "yaml", "requests"]


def requirements_hash() -> str:
    return hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()


def check_python() -> int:
    version = sys.version_info[:2]
    print(f"Python detectado: {sys.version.split()[0]} ({sys.executable})")
    if version < MIN_VERSION:
        print(f"ERROR: se requiere Python {MIN_VERSION[0]}.{MIN_VERSION[1]} o superior.")
        return 2
    if version > MAX_TESTED:
        print(f"AVISO: Python {version[0]}.{version[1]} es más reciente que la versión validada "
              f"({MAX_TESTED[0]}.{MAX_TESTED[1]}). Si la instalación falla, usa Python 3.11 o 3.12.")
    return 0


def check_installed() -> int:
    if not MARKER.is_file() or MARKER.read_text(encoding="utf-8").strip() != requirements_hash():
        return 1
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            return 1
    return 0


def mark_installed() -> int:
    missing = []
    for module in REQUIRED_MODULES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        print("ERROR: faltan módulos después de instalar: " + ", ".join(missing))
        return 1
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(requirements_hash(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "python"
    handlers = {"python": check_python, "installed": check_installed, "mark-installed": mark_installed}
    if command not in handlers:
        print(__doc__)
        sys.exit(64)
    sys.exit(handlers[command]())
