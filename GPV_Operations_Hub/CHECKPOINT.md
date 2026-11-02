# Checkpoint del proyecto

Versión: **1.0.0** · Fecha: 2026-11-02 · Estado: todos los módulos del encargo implementados e
integrados sobre el mismo modelo de datos y permisos; pruebas automatizadas, E2E y validación desde
extracción limpia ejecutadas (ver `TEST_RESULTS.md`).

## Hecho

1. Base y permisos (roles configurables, áreas, archivos privados, auditoría, notificaciones, trabajos, diagnóstico, respaldo).
2. Importación y modelo de producción (asistente completo, snapshots, reversión, compensación).
3. Métricas, dashboards (con constructor), reportes en 5 formatos y planificador.
4. Comunicados, comentarios/incidencias, conversaciones y Kaizen con A3.
5. Hoja de cálculo con motor de fórmulas propio, versiones y conflictos.
6. Centro de documentos (PDF, PPTX, XLSX/CSV, DOCX, LibreOffice opcional).
7. Etiquetas: diseñador, Code 128/QR, SVG/PDF/ZPL, impresión con estados honestos.
8. Integración, 64 pruebas (SQLite, PostgreSQL, Python 3.11/3.12/3.13), E2E 45/45, rendimiento, documentación y ZIP.

## Pendiente (requiere recursos externos)

| Tarea | Responsable sugerido | Referencia |
|---|---|---|
| Validar etiquetas en impresoras físicas (tamaño, lectura, alineación, ZPL, colas) | Calidad + Mantenimiento | GUIA_VALIDACION_ETIQUETAS.md |
| Instalar en servidor Windows con Waitress, HTTPS, PostgreSQL y servicios | TI | DESPLIEGUE_INTERNO.md |
| Instalar LibreOffice (y opcionalmente Tesseract) en el servidor | TI | LIMITACIONES.md |
| Prueba de carga en el servidor real | TI | `tools/load_test.py`, `gpv_benchmark` |
| Cargar logotipo oficial y datos reales mediante el asistente | Administrador | GUIA_USUARIO_ES.md |

## Cómo continuar el desarrollo

* Código: `apps/<módulo>`; plantillas en `templates/`; JS/CSS en `static/gpv/`.
* Pruebas: `.venv\Scripts\python.exe manage.py test`. E2E (opcional, requiere Node+Playwright):
  `node tools/e2e_smoke.js http://127.0.0.1:8000 <usuario> <contraseña>`.
* Empaquetar: `.venv\Scripts\python.exe tools\build_release.py --output ..\dist`.
* Mejoras posibles (no comprometidas): Data Matrix/GS1, adaptadores de integración (FactoryLogix,
  Dynamics) sobre la capa de importación, WebSockets para notificaciones, más funciones de hoja.
