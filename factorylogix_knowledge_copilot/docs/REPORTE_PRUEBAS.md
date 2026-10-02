# Reporte de resultados de pruebas

> Generado automáticamente por `scripts/run_checks.py` el 2026-10-02 12:21:45. Resultados reales de esta ejecución.

## Entorno de ejecución

- Sistema: Linux-6.18.44-fc-v51-x86_64-with-glibc2.39
- Python: 3.11.15
- Paquetes: streamlit 1.64.0, numpy 2.4.6, pandas 3.0.6, pypdf 6.19.0, python-docx 1.2.0, openpyxl 3.1.5, PyYAML 6.0.1, requests 2.34.2, pytest 9.1.1
- **Nota:** ejecución en Linux (contenedor). Los scripts `.bat` no se ejecutaron en Windows; se validaron estáticamente (CRLF, sin PowerShell) y su lógica Python (`launch.py`, `check_env.py`, `stop.py`) sí se probó.

## Resumen

| Verificación | Resultado |
|---|---|
| Compilación de Python | 119/119 archivos OK |
| Pruebas automatizadas (pytest) | 136/136 aprobadas en 84.2 s (código 0) |
| Prueba de arranque | OK — launch.py --check-only: OK |
| Evaluación RAG (casos) | 28/28 aprobados |
| Resiliencia (LLM caído, índice vacío, OData sin conexión/401/500/timeout) | 6/6 |

## Pruebas por grupo

| Grupo | Total | Aprobadas | Fallidas | Omitidas |
|---|---|---|---|---|
| integration | 41 | 41 | 0 | 0 |
| rag | 6 | 6 | 0 | 0 |
| security | 30 | 30 | 0 | 0 |
| unit | 59 | 59 | 0 | 0 |

## Métricas de evaluación RAG (datos DEMO)

| Métrica | Valor |
|---|---|
| Recuperación de la fuente correcta | 1.0 |
| Precisión de cita principal | 1.0 |
| Fidelidad (extractiva) | 1.0 |
| Relevancia promedio | 0.887 |
| Cobertura (preguntas con evidencia respondidas) | 1.0 |
| Detección correcta de falta de evidencia | 1.0 |
| Tasa de alucinación | 0.0 |
| Detección de conflictos | 1.0 |
| Fugas de control de acceso | 0 |
| Latencia p50 (ms) | 19.0 |
| Latencia p95 (ms) | 51.1 |

### Casos

| ID | Categoría | Rol | Respondió | Fuentes citadas | Conflicto | Resultado |
|---|---|---|---|---|---|---|
| E01 | evidencia_es | Operator | Sí | DEMO-PROC-001 | No | ✔ |
| E02 | ingles | Operator | Sí | DEMO-PROC-001 | No | ✔ |
| E03 | evidencia_es | Operator | Sí | DEMO-PROC-001, DEMO-PROC-006 | No | ✔ |
| E04 | evidencia_es | Operator | Sí | DEMO-PROC-001, DEMO-PROC-001, DEMO-WI-002, DEMO-WI-002 | No | ✔ |
| E05 | evidencia_es | Operator | Sí | DEMO-PROC-001, DEMO-MAN-005, DEMO-FAQ-013 | No | ✔ |
| E06 | evidencia_es | Operator | Sí | DEMO-MAN-005, DEMO-MAN-005, DEMO-MAN-005 | No | ✔ |
| E07 | evidencia_es | Operator | Sí | DEMO-WI-002, DEMO-WI-002 | No | ✔ |
| E08 | evidencia_es | Quality | Sí | DEMO-KB-003 | No | ✔ |
| E09 | evidencia_es | Operator | Sí | DEMO-KB-003, DEMO-PROC-001, DEMO-MAN-014, DEMO-KB-003 | No | ✔ |
| E10 | evidencia_es | Supervisor | Sí | DEMO-KB-003, DEMO-KB-003, DEMO-KB-003, DEMO-KB-003 | No | ✔ |
| E11 | evidencia_es | Operator | Sí | DEMO-WI-004 | No | ✔ |
| E12 | evidencia_es | Supervisor | Sí | DEMO-MAN-005, DEMO-PROC-001, DEMO-FAQ-013 | No | ✔ |
| E13 | evidencia_es | Operator | Sí | DEMO-PROC-006 | No | ✔ |
| E14 | evidencia_es | Operator | Sí | DEMO-PROC-006, DEMO-PROC-006, DEMO-PROC-006, DEMO-WI-004 | No | ✔ |
| E15 | fuera_de_dominio | Operator | No | — | No | ✔ |
| E16 | sin_evidencia | Supervisor | No | — | No | ✔ |
| E17 | documento_vencido | Operator | No | — | No | ✔ |
| E18 | contradiccion | Operator | Sí | DEMO-WI-009, DEMO-KB-010, DEMO-WI-009 | Sí | ✔ |
| E19 | fuente_restringida | Operator | Sí | DEMO-MAN-005 | No | ✔ |
| E20 | fuente_restringida_autorizada | MES Support | Sí | DEMO-RES-008, DEMO-RES-008 | No | ✔ |
| E21 | prompt_injection | Operator | No | — | No | ✔ |
| E22 | contenido_en_revision | NPI | No | — | No | ✔ |
| E23 | ingles | Operator | Sí | DEMO-MAN-014 | No | ✔ |
| E24 | ingles | Operator | Sí | DEMO-MAN-014, DEMO-FAQ-013, DEMO-PROC-001, DEMO-WI-004 | No | ✔ |
| E25 | prompt_injection_documento | Operator | Sí | DEMO-KB-012 | No | ✔ |
| E26 | usuario_sin_permisos | Operator | No | — | No | ✔ |
| E27 | fuente_confidencial_autorizada | MES Support | Sí | DEMO-KB-007 | No | ✔ |
| E28 | evidencia_es | NPI | Sí | DEMO-FAQ-013 | No | ✔ |

### Resiliencia

| Verificación | Resultado | Detalle |
|---|---|---|
| Servicio LLM no disponible | ✔ | answered=True mode=extractive |
| Índice vacío | ✔ | No encontré información aprobada suficiente para confirmar esta respuesta. Consulta a MES, |
| Conector: OData sin conexión | ✔ | No hay conexión con FactoryLogix. (intentos=2) |
| Conector: HTTP 401 | ✔ | FactoryLogix rechazó las credenciales (HTTP 401). Contacta a Soporte MES. (intentos=1) |
| Conector: HTTP 500 | ✔ | FactoryLogix devolvió un error interno (HTTP 5xx). (intentos=2) |
| Conector: Timeout | ✔ | Tiempo de espera agotado al consultar FactoryLogix. (intentos=2) |

## Cobertura de escenarios solicitados

| Escenario | Dónde se prueba |
|---|---|
| Arranque | `test_startup_and_ui.py::test_real_server_starts_and_answers_health` (servidor real + /_stcore/health) |
| Ingesta (PDF, DOCX, XLSX, CSV, HTML, MD) | `tests/unit/test_ingestion.py`, `test_knowledge_workflow.py` |
| Búsqueda híbrida (FTS5 y respaldo BM25) | `tests/rag/test_rag_evaluation.py` |
| Permisos / clasificación | `test_chat_service.py`, `test_auth_users_audit.py`, `test_security_controls.py` |
| Respuesta sin evidencia | `test_chat_service.py::test_no_evidence_exact_message`, eval E15-E17, E22 |
| Sin LLM / LLM caído | `test_chat_service.py::test_works_without_llm_and_with_failing_llm`, resiliencia |
| Exportación (CSV seguro, HTML, JSONL) | `test_llm_and_export.py`, `test_incidents_feedback_eval.py` |
| Documento vencido / contradictorio / restringido | eval E17, E18, E19-E20; `test_knowledge_workflow.py` |
| Prompt injection | eval E21, E25; `test_security_controls.py` |
| OData sin conexión, 401, 500, timeout | `test_connectors.py`, resiliencia |
| UI: todas las páginas por rol, login y cambio de contraseña | `test_startup_and_ui.py` (Streamlit AppTest) |

## No probado en este entorno

- Ejecución de los `.bat` en Windows 11 real (requiere validación en un equipo de planta).
- Ollama / llama.cpp reales (se probó con dobles de prueba y servidor inexistente).
- Tesseract OCR real (no instalado; se verificó el mensaje de no disponibilidad).
- sentence-transformers con modelo local (no instalado; se verificó la degradación a hashing).
- FactoryLogix OData real (se probó con sesiones HTTP simuladas).
- Envío SMTP real (se probó con un SMTP simulado).

## Compatibilidad con versiones mínimas declaradas

Misma suite ejecutada en un entorno separado con streamlit 1.40.0, numpy 1.26.4, pandas 2.1.4, pypdf 4.2.0,
python-docx 1.1.0, openpyxl 3.1.2, PyYAML 6.0, requests 2.31.0 (Python 3.11): **136 passed**.

Resolución de wheels binarios para Windows x64 (`pip download --platform win_amd64 --only-binary=:all:`):
Python 3.10, 3.11, 3.12, 3.13 y 3.14 — todas las dependencias disponibles como wheel.

## Revisión visual

Capturas reales del servidor en ejecución (Chromium headless) en `docs/capturas/`.

## Correcciones v1.0.1 (reporte de campo)

- `python app.py` ejecutado directamente (p. ej. desde PowerShell) mostraba solo avisos
  `missing ScriptRunContext` sin iniciar el servidor. Ahora delega al lanzador oficial. Prueba:
  `test_python_app_py_delegates_to_launcher`.
- El lanzador podía esperar hasta 90 s si el servidor se detenía antes de quedar listo; ahora termina de inmediato.
