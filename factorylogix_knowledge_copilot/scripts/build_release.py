"""Empaqueta la versión distribuible en dist/FactoryLogix_Knowledge_Copilot_v<versión>.zip.

Excluye entornos virtuales, bases de datos, logs, reportes generados, archivos cargados, secretos (.env),
cachés y scripts temporales. Verifica el ZIP (sin archivos vacíos, sin secretos, con archivos obligatorios).
Uso: python scripts/build_release.py
"""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOP = "factorylogix_knowledge_copilot"
EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache", "dist", "wheelhouse", "models_local", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".db", ".db-wal", ".db-shm", ".log", ".zip", ".pid"}
REQUIRED = ["app.py", "requirements.txt", "pyproject.toml", "README.md", ".env.example", "INSTALAR_WINDOWS.bat",
            "INICIAR_WINDOWS.bat", "DETENER_WINDOWS.bat", "config/settings.yaml", "database/schema.sql",
            "docs/ARQUITECTURA.md", "docs/MODELO_AMENAZAS.md", "docs/MATRIZ_RBAC.md", "docs/REPORTE_PRUEBAS.md",
            "demo_data/manifest.yaml", "tests/conftest.py"]


def include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if set(parts) & EXCLUDE_DIRS or path.suffix in EXCLUDE_SUFFIXES or path.name.startswith("scratch_"):
        return False
    if path.name == ".env":
        return False
    if parts[0] in {"data", "logs", "reports"} and path.name != "README.md":
        return False
    if parts[:2] == ("knowledge_base", "files"):
        return False
    return path.is_file()


def main() -> int:
    version = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))["app"]["version"]
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / f"FactoryLogix_Knowledge_Copilot_v{version}.zip"
    files = sorted(p for p in ROOT.rglob("*") if include(p))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            zf.write(path, arcname=f"{TOP}/{path.relative_to(ROOT).as_posix()}")
        for folder in ("knowledge_base/files/", "data/backups/"):
            zf.writestr(f"{TOP}/{folder}", "")  # carpetas vacías necesarias (entradas de directorio)

    with zipfile.ZipFile(target) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        names = {i.filename[len(TOP) + 1:] for i in infos}
        empty = [i.filename for i in infos if i.file_size == 0]
        missing = [r for r in REQUIRED if r not in names]
        forbidden = [n for n in names if n.endswith((".db", ".env")) or n == ".env" or "PRIMER_ACCESO" in n
                     or "USUARIOS_DEMO" in n]
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"ZIP: {target}")
    print(f"Archivos: {len(infos)} · Tamaño: {target.stat().st_size / 1024:.0f} KB · SHA-256: {digest}")
    problems = [f"vacío: {e}" for e in empty] + [f"falta: {m}" for m in missing] + [f"prohibido: {f}" for f in forbidden]
    for problem in problems:
        print("ERROR", problem)
    (dist / f"{target.name}.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
