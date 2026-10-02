"""Genera documentación derivada del código para evitar divergencias:

- docs/MATRIZ_RBAC.md                    (desde security/rbac.py y config/settings.yaml)
- docs/INVENTARIO_DEPENDENCIAS_LICENCIAS.md (desde los metadatos de paquetes instalados)
- docs/ARBOL_CARPETAS.md                 (estructura del proyecto)

Uso: python scripts/generate_docs.py
"""
from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_settings  # noqa: E402
from models.domain import Role  # noqa: E402
from security.rbac import DETAIL_LEVEL, P, ROLE_PERMISSIONS, AccessPolicy  # noqa: E402

DOCS = ROOT / "docs"
SKIP = {".venv", "__pycache__", ".pytest_cache", "dist", "wheelhouse", "models_local", ".git"}


def rbac() -> str:
    roles = Role.values()
    lines = ["# Matriz RBAC", "", "> Generado automáticamente por `scripts/generate_docs.py` desde "
             "`security/rbac.py` y `config/settings.yaml`. No editar a mano.", "",
             "## Permisos por rol", "", "| Permiso | Descripción | " + " | ".join(roles) + " |",
             "|---|---|" + "|".join(":-:" for _ in roles) + "|"]
    for perm, desc in P.items():
        marks = " | ".join("✔" if perm in ROLE_PERMISSIONS[r] else "" for r in roles)
        lines.append(f"| `{perm}` | {desc} | {marks} |")
    policy = AccessPolicy(load_settings(environ={}).get("access_matrix"))
    levels = ["Public", "Internal", "Confidential", "Restricted"]
    lines += ["", "## Acceso por clasificación de información", "",
              "| Rol | " + " | ".join(levels) + " | Profundidad de respuesta |", "|---|" + "|".join(":-:" for _ in levels)
              + "|---|"]
    for role in roles:
        allowed = policy.clearance_for(role)
        lines.append(f"| {role} | " + " | ".join("✔" if lvl in allowed else "—" for lvl in levels)
                     + f" | {DETAIL_LEVEL[role]} |")
    lines += ["", "## Principios", "",
              "- Mínimo privilegio: el Operador solo consulta conocimiento aprobado y crea escalamientos.",
              "- Segregación de funciones: quien carga una versión no puede aprobarla (`governance.require_four_eyes`).",
              "- El Auditor tiene acceso de solo lectura a evidencias y registros; no modifica contenido.",
              "- La clasificación se filtra ANTES del ranking: el contenido no autorizado nunca llega a la respuesta.",
              "- Los intentos de recuperar fuentes no autorizadas quedan en auditoría (`rag.restricted_source_denied`)."]
    return "\n".join(lines) + "\n"


def licenses() -> str:
    direct = [re.split(r"[<>=!~ ]", l.strip())[0] for l in (ROOT / "requirements.txt").read_text().splitlines()
              if l.strip() and not l.startswith("#")]
    seen: dict[str, tuple[str, str, str, str]] = {}

    def visit(name: str, kind: str) -> None:
        key = name.lower().replace("_", "-")
        if key in seen:
            return
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            return
        meta = dist.metadata
        lic = meta.get("License-Expression") or ""
        if not lic or len(lic) > 60:
            classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if "License ::" in c]
            lic = ", ".join(classifiers) or (meta.get("License") or "ver paquete")[:60]
        seen[key] = (meta["Name"], dist.version, lic.replace("\n", " "), kind)
        for req in dist.requires or []:
            if "extra ==" in req:
                continue
            visit(re.split(r"[<>=!~ ;\[(]", req)[0], "transitiva")

    for name in direct:
        visit(name, "directa")
    for name in direct:
        key = name.lower().replace("_", "-")
        if key in seen:
            seen[key] = (*seen[key][:3], "directa")
    lines = ["# Inventario de dependencias y licencias", "",
             "> Generado por `scripts/generate_docs.py` a partir de los paquetes instalados en el entorno de "
             "pruebas (Linux, Python " + sys.version.split()[0] + "). Las versiones en Windows pueden variar "
             "dentro de los rangos de `requirements.txt`. Validar con el área legal antes de producción.", "",
             "| Paquete | Versión probada | Licencia | Tipo |", "|---|---|---|---|"]
    for name, version, lic, kind in sorted(seen.values(), key=lambda x: (x[3] != "directa", x[0].lower())):
        lines.append(f"| {name} | {version} | {lic} | {kind} |")
    lines += ["", "## Componentes opcionales (no incluidos)", "",
              "| Componente | Licencia | Uso |", "|---|---|---|",
              "| sentence-transformers + torch + modelo multilingüe | Apache-2.0 / BSD (verificar modelo) | "
              "Embeddings semánticos locales |",
              "| Tesseract OCR + pytesseract | Apache-2.0 | OCR de imágenes escaneadas |",
              "| Ollama / llama.cpp | MIT | LLM local opcional (verificar licencia del modelo elegido) |",
              "", "No se usan servicios de nube, API de OpenAI ni API de Claude."]
    return "\n".join(lines) + "\n"


def tree() -> str:
    lines = ["# Árbol de carpetas", "", "> Generado por `scripts/generate_docs.py`.", "", "```text",
             "factorylogix_knowledge_copilot/"]

    def walk(folder: Path, prefix: str) -> None:
        entries = sorted([p for p in folder.iterdir() if p.name not in SKIP and not p.name.startswith("scratch_")
                          and not (p.is_dir() and p.name == "files" and folder.name == "knowledge_base")
                          and p.suffix not in {".pyc", ".db", ".log", ".zip"}],
                         key=lambda p: (p.is_file(), p.name.lower()))
        for i, entry in enumerate(entries):
            last = i == len(entries) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{entry.name}{'/' if entry.is_dir() else ''}")
            if entry.is_dir() and entry.name not in {"data", "logs", "reports"}:
                walk(entry, prefix + ("    " if last else "│   "))

    walk(ROOT, "")
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "MATRIZ_RBAC.md").write_text(rbac(), encoding="utf-8")
    (DOCS / "INVENTARIO_DEPENDENCIAS_LICENCIAS.md").write_text(licenses(), encoding="utf-8")
    (DOCS / "ARBOL_CARPETAS.md").write_text(tree(), encoding="utf-8")
    print("Documentación generada en", DOCS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
