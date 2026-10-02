"""Ejecuta las verificaciones de calidad y genera docs/REPORTE_PRUEBAS.md con resultados REALES.

Pasos: compilación de todos los .py, pytest (unitarias, integración, seguridad, RAG con junit), evaluación RAG
en un entorno temporal y prueba de arranque (--check-only). Uso: python scripts/run_checks.py
"""
from __future__ import annotations

import os
import platform
import py_compile
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SKIP = {".venv", "__pycache__", "dist", "wheelhouse", ".pytest_cache"}


def compile_all() -> tuple[int, list[str]]:
    errors, count = [], 0
    for path in ROOT.rglob("*.py"):
        if set(path.relative_to(ROOT).parts) & SKIP:
            continue
        count += 1
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc.msg}")
    return count, errors


def run_pytest(junit: Path) -> tuple[int, dict[str, dict[str, int]], float, list[str]]:
    started = time.time()
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests", "-o", "addopts=", "-q", "-p", "no:cacheprovider",
                           f"--junitxml={junit}"], cwd=ROOT, capture_output=True, text=True)
    elapsed = time.time() - started
    groups: dict[str, dict[str, int]] = {}
    failures = []
    for case in ET.parse(junit).getroot().iter("testcase"):
        group = case.get("classname", "").split(".")[1] if "." in case.get("classname", "") else "otros"
        stats = groups.setdefault(group, {"total": 0, "passed": 0, "failed": 0, "skipped": 0})
        stats["total"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            stats["failed"] += 1
            failures.append(f"{case.get('classname')}::{case.get('name')}")
        elif case.find("skipped") is not None:
            stats["skipped"] += 1
        else:
            stats["passed"] += 1
    return proc.returncode, groups, elapsed, failures


def run_evaluation() -> dict:
    from core.config import load_settings
    from models.domain import SYSTEM_USER
    from services.container import build_container

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        settings = load_settings(environ={}, overrides={
            "paths.data_dir": str(base / "data"), "paths.database": str(base / "data" / "eval.db"),
            "paths.files_dir": str(base / "files"), "paths.attachments_dir": str(base / "att"),
            "paths.reports_dir": str(base / "rep"), "paths.logs_dir": str(base / "logs")})
        container = build_container(settings)
        result = container.evaluation.run(SYSTEM_USER)
        container.evaluation.export(result, ROOT / "reports")
        return result


def run_startup_check() -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "FLKC_DATA_DIR": f"{tmp}/data", "FLKC_DATABASE": f"{tmp}/data/s.db",
               "FLKC_FILES_DIR": f"{tmp}/files", "FLKC_LOGS_DIR": f"{tmp}/logs", "FLKC_REPORTS_DIR": f"{tmp}/rep",
               "FLKC_ATTACHMENTS_DIR": f"{tmp}/att"}
        proc = subprocess.run([sys.executable, "scripts/launch.py", "--check-only", "--no-browser"], cwd=ROOT,
                              env=env, capture_output=True, text=True, timeout=300)
        ok = proc.returncode == 0 and "Verificación completada" in proc.stdout
        return ok, "launch.py --check-only: " + ("OK" if ok else proc.stdout[-300:] + proc.stderr[-300:])


def versions() -> str:
    names = ["streamlit", "numpy", "pandas", "pypdf", "python-docx", "openpyxl", "PyYAML", "requests", "pytest"]
    parts = []
    for name in names:
        try:
            parts.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            parts.append(f"{name} (no instalado)")
    return ", ".join(parts)


def main() -> int:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    compiled, compile_errors = compile_all()
    junit = Path(tempfile.gettempdir()) / "flkc_junit.xml"
    code, groups, elapsed, failures = run_pytest(junit)
    evaluation = run_evaluation()
    startup_ok, startup_detail = run_startup_check()
    s = evaluation["summary"]
    total = sum(g["total"] for g in groups.values())
    passed = sum(g["passed"] for g in groups.values())
    lines = [
        "# Reporte de resultados de pruebas", "",
        f"> Generado automáticamente por `scripts/run_checks.py` el {stamp}. Resultados reales de esta ejecución.", "",
        "## Entorno de ejecución", "",
        f"- Sistema: {platform.platform()}", f"- Python: {sys.version.split()[0]}", f"- Paquetes: {versions()}",
        "- **Nota:** ejecución en Linux (contenedor). Los scripts `.bat` no se ejecutaron en Windows; se validaron "
        "estáticamente (CRLF, sin PowerShell) y su lógica Python (`launch.py`, `check_env.py`, `stop.py`) sí se probó.",
        "", "## Resumen", "",
        "| Verificación | Resultado |", "|---|---|",
        f"| Compilación de Python | {compiled - len(compile_errors)}/{compiled} archivos OK |",
        f"| Pruebas automatizadas (pytest) | {passed}/{total} aprobadas en {elapsed:.1f} s (código {code}) |",
        f"| Prueba de arranque | {'OK' if startup_ok else 'FALLÓ'} — {startup_detail} |",
        f"| Evaluación RAG (casos) | {s['cases_passed']}/{s['cases']} aprobados |",
        f"| Resiliencia (LLM caído, índice vacío, OData sin conexión/401/500/timeout) | {s['resilience_passed']} |",
        "", "## Pruebas por grupo", "", "| Grupo | Total | Aprobadas | Fallidas | Omitidas |", "|---|---|---|---|---|"]
    for name, g in sorted(groups.items()):
        lines.append(f"| {name} | {g['total']} | {g['passed']} | {g['failed']} | {g['skipped']} |")
    if failures:
        lines += ["", "### Fallas", ""] + [f"- {f}" for f in failures]
    if compile_errors:
        lines += ["", "### Errores de compilación", ""] + [f"- {e}" for e in compile_errors]
    lines += ["", "## Métricas de evaluación RAG (datos DEMO)", "", "| Métrica | Valor |", "|---|---|"]
    labels = {"retrieval_hit_rate": "Recuperación de la fuente correcta", "citation_precision": "Precisión de cita principal",
              "faithfulness_avg": "Fidelidad (extractiva)", "relevance_avg": "Relevancia promedio",
              "coverage": "Cobertura (preguntas con evidencia respondidas)",
              "no_evidence_accuracy": "Detección correcta de falta de evidencia", "hallucination_rate": "Tasa de alucinación",
              "conflict_detection": "Detección de conflictos", "access_control_leaks": "Fugas de control de acceso",
              "latency_p50_ms": "Latencia p50 (ms)", "latency_p95_ms": "Latencia p95 (ms)"}
    for key, label in labels.items():
        lines.append(f"| {label} | {s.get(key)} |")
    lines += ["", "### Casos", "", "| ID | Categoría | Rol | Respondió | Fuentes citadas | Conflicto | Resultado |",
              "|---|---|---|---|---|---|---|"]
    for d in evaluation["details"]:
        lines.append(f"| {d['id']} | {d['category']} | {d['role']} | {'Sí' if d['answered'] else 'No'} | "
                     f"{d['cited'] or '—'} | {'Sí' if d['conflict_detected'] else 'No'} | "
                     f"{'✔' if d['passed'] else '✖'} |")
    lines += ["", "### Resiliencia", "", "| Verificación | Resultado | Detalle |", "|---|---|---|"]
    for r in evaluation["resilience"]:
        lines.append(f"| {r['check']} | {'✔' if r['passed'] else '✖'} | {r['detail']} |")
    lines += ["", "## Cobertura de escenarios solicitados", "",
              "| Escenario | Dónde se prueba |", "|---|---|",
              "| Arranque | `test_startup_and_ui.py::test_real_server_starts_and_answers_health` (servidor real + /_stcore/health) |",
              "| Ingesta (PDF, DOCX, XLSX, CSV, HTML, MD) | `tests/unit/test_ingestion.py`, `test_knowledge_workflow.py` |",
              "| Búsqueda híbrida (FTS5 y respaldo BM25) | `tests/rag/test_rag_evaluation.py` |",
              "| Permisos / clasificación | `test_chat_service.py`, `test_auth_users_audit.py`, `test_security_controls.py` |",
              "| Respuesta sin evidencia | `test_chat_service.py::test_no_evidence_exact_message`, eval E15-E17, E22 |",
              "| Sin LLM / LLM caído | `test_chat_service.py::test_works_without_llm_and_with_failing_llm`, resiliencia |",
              "| Exportación (CSV seguro, HTML, JSONL) | `test_llm_and_export.py`, `test_incidents_feedback_eval.py` |",
              "| Documento vencido / contradictorio / restringido | eval E17, E18, E19-E20; `test_knowledge_workflow.py` |",
              "| Prompt injection | eval E21, E25; `test_security_controls.py` |",
              "| OData sin conexión, 401, 500, timeout | `test_connectors.py`, resiliencia |",
              "| UI: todas las páginas por rol, login y cambio de contraseña | `test_startup_and_ui.py` (Streamlit AppTest) |",
              "", "## No probado en este entorno", "",
              "- Ejecución de los `.bat` en Windows 11 real (requiere validación en un equipo de planta).",
              "- Ollama / llama.cpp reales (se probó con dobles de prueba y servidor inexistente).",
              "- Tesseract OCR real (no instalado; se verificó el mensaje de no disponibilidad).",
              "- sentence-transformers con modelo local (no instalado; se verificó la degradación a hashing).",
              "- FactoryLogix OData real (se probó con sesiones HTTP simuladas).",
              "- Envío SMTP real (se probó con un SMTP simulado)."]
    (ROOT / "docs" / "REPORTE_PRUEBAS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:22]))
    ok = code == 0 and not compile_errors and startup_ok and s["cases_passed"] == s["cases"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
