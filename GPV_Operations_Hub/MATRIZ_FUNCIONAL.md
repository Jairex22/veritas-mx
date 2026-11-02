# Matriz funcional

Estado: **Probado (auto)** = prueba automatizada que verifica resultados independientes ·
**Probado (E2E)** = recorrido en navegador real (Chromium, escritorio y móvil) ·
**Revisado** = verificado manualmente en esta sesión · **Pendiente físico** = requiere impresora real ·
**Pendiente infra** = requiere infraestructura corporativa · **Requiere motor** = depende de un motor externo opcional.
Las pruebas se ubican en `apps/<app>/tests/` (número = criterio de aceptación del encargo).

| # | Requisito | Implementación | Dependencia | Prueba | Estado |
|---|---|---|---|---|---|
| 1 | Sitio web responsive, URL única, sin instalar en cliente | Django + plantillas + CSS/JS propios, sin CDN | — | E2E escritorio y móvil (`tools/e2e_smoke.js`) | Probado (E2E) |
| 2 | Inicio de sesión, roles configurables, permisos en servidor y por área | `core/permissions.py`, matriz `RoleCapability`, `filter_by_area` | — | `core/tests/test_security.py` (12), `production/tests/test_metrics.py::test_area_isolation` | Probado (auto) |
| 3 | Comunicados por área/turno/grupo/rol, prioridad, vigencia, adjuntos, confirmación | `apps/comms` | — | `comms/tests/test_comms.py` (11) | Probado (auto) |
| 4 | Comentarios, dudas, incidencias vinculadas; conversaciones; notificaciones leído/no leído | `Comment` genérico, `Conversation`, `Notification`, sondeo configurable | — | `test_comms.py::test_comments_and_incidents_on_order`, E2E | Probado (auto/E2E) |
| 5 | Asistente XLSX/CSV: detección, vista previa, mapeo, claves, validación fila/columna, resumen conciliado | `production/readers.py`, `importer.py`, vistas del asistente | — | `test_import.py` (1, 2) | Probado (auto) |
| 6 | Seriales como texto, ceros iniciales, daño >15 dígitos | `parsing.py`, `readers.py` (formato 000000) | — | `test_import.py::test_05` | Probado (auto) |
| 7 | Fechas ambiguas y decimales: confirmación explícita | `parse_date_text`, `parse_decimal`, evidencia por columna | — | `test_import.py::test_ambiguous_dates_require_choice` | Probado (auto) |
| 8 | Incremental vs snapshot vs serial; no sumar snapshots | `DatasetKind`, supersede con historial | — | `test_import.py::test_04` | Probado (auto) |
| 9 | Duplicados por clave y hash; reimportar no duplica | clave de registro, aviso de hash previo | — | `test_import.py::test_03` | Probado (auto) |
| 10 | Anexar / actualizar por clave / reemplazar alcance con vista previa | `plan_changes` | — | `test_import.py` (03, revert) | Probado (auto) |
| 11 | Perfiles de mapeo, historial, archivo original, revertir sin destruir posteriores | `MappingProfile`, `ImportBatch`, `RecordChange`, `revert()` | — | `test_import.py::test_revert_keeps_later_changes` | Probado (auto) |
| 12 | Falla no deja importación parcial sin identificar | bloques atómicos + compensación + estado FAILED | — | `test_import.py::test_failure_mid_import_is_compensated` | Probado (auto) |
| 13 | Fórmulas de Excel: valor almacenado vs calculado; nunca 0 silencioso | `read_xlsx` + motor interno | — | `test_import.py::test_formula_without_cached_value…` | Probado (auto) |
| 14 | Lotes grandes por bloques con progreso y límites | `IMPORT_CHUNK_ROWS`, `IMPORT_MAX_ROWS`, `JobContext.progress` | — | Benchmark 100 000 filas (SQLite y PostgreSQL) | Probado (medido) |
| 15 | Plan: vistas hoy/semana/mes/rango, filtros, meta/avance/pendiente/vencimiento/fuente/antigüedad | `metrics.order_rows`, `production/plan.html` | — | E2E, `test_metrics.py` | Probado (auto/E2E) |
| 16 | Cambios de meta/prioridad con motivo e historial; no sobreescribir silenciosamente | `order_edit` con versión, `PlanChange`, importación de plan con diff | — | `test_security.py::test_operator_only_captures_assigned_orders` | Probado (auto) |
| 17 | Reglas KPI (cumplimiento agrupado 76.67 %, pendiente 70, no calculable, datos insuficientes) | `metrics.py` | — | `test_metrics.py` (6, 7) | Probado (auto) |
| 18 | FPY desde primer intento; OEE con insumos reales | `fpy()`, `oee()` | — | `test_metrics.py::test_07b` | Probado (auto) |
| 19 | Proyección con fórmula, ventana y supuestos | `projection()` | — | Revisión manual en detalle de orden | Revisado |
| 20 | Dashboards: tarjetas, barras, tendencias, Pareto, atrasos, Kaizen, filtrado cruzado, detalle, exportar selección | `dashboard.js`, `charts.js`, `reports/views.py` | — | E2E (clic en barra filtra), `test_metrics.py::test_08` | Probado (auto/E2E) |
| 21 | Constructor de dashboards: dimensión, medida, agregación, gráfico, orden, guardar/duplicar/compartir | `board.js`, `Dashboard`, `board_save` (versión) | — | Revisado manualmente; validación de servidor | Revisado |
| 22 | Campos calculados seguros y unión con validación de cardinalidad | `safe_calc` (sin eval), `validate_plan_join` | — | Revisado; configurado en datos demo | Revisado |
| 23 | Tabla = gráfico = Excel = PDF para mismos filtros | capa común + instantánea | — | `test_metrics.py::test_08` | Probado (auto) |
| 24 | Reportes diario, semanal, atrasos, calidad, por línea, Kaizen en PDF/XLSX/CSV/DOCX/PPTX | `snapshot.py`, `exporters.py` | — | `test_reports.py::test_all_formats_and_templates_generate`, E2E | Probado (auto/E2E) |
| 25 | Reportes programados una sola vez, recuperación, zona MX, notificación | `scheduler_tick`, restricción única, lease, `run_scheduler` | Proceso planificador | `test_reports.py` (13, concurrencia, ocurrencias perdidas) | Probado (auto) |
| 26 | Hoja: hojas, edición, rangos, copiar/pegar, deshacer, filas/columnas, ordenar, filtrar, buscar, congelar, anchos | `sheet.js`, `sheets/engine.py` | — | E2E (editar, fórmula, guardar), `test_sheets.py` | Probado (E2E/auto) |
| 27 | Formatos, formato condicional, validación, protección, agrupación, tabla dinámica | `sheet.js`, `engine.pivot/check_validations/protected_violations` | — | `test_sheets.py::test_pivot`, `test_protected_columns_server_side` | Probado (auto) parcial; UI revisada |
| 28 | Fórmulas soportadas, ciclos, #DIV/0!, desconocidas; sin eval | `sheets/formula.py` | — | `test_sheets.py` (9) | Probado (auto) |
| 29 | Importar/exportar XLSX/CSV preservando tipos; avisar pérdidas | `engine.from_xlsx/to_xlsx/to_csv` | — | `test_sheets.py::test_xlsx_roundtrip…` | Probado (auto) |
| 30 | Versiones, conflictos de edición, publicación validada al dataset | `WorkbookVersion`, 409, `publish` → asistente | — | `test_sheets.py` (10) | Probado (auto) |
| 31 | Centro de documentos: carpetas, etiquetas, búsqueda, permisos, vista previa, lote, ZIP | `apps/documents` | — | `test_documents.py`, E2E | Probado (auto/E2E) |
| 32 | PDF: combinar, cortar, organizar con miniaturas, extraer, duplicar, rotar, recortar, numerar, marca, texto, imágenes↔PDF, texto, comprimir, protegidos | `ops_pdf.py`, `organizer.js` | — | `test_documents.py` (14 y otras) | Probado (auto) |
| 33 | PPTX: listar, miniaturas, extraer/eliminar/duplicar/reordenar, combinar con temas, avisos | `ops_pptx.py` (nivel OPC) | Miniaturas/PDF: LibreOffice | `test_documents.py` (15, merge) | Probado (auto) |
| 34 | XLSX/CSV: hojas, dividir, combinar, duplicados, limpieza, separadores, PDF de rangos | `ops_tabular.py` | — | `test_documents.py` (16, xlsx) | Probado (auto) |
| 35 | DOCX: estructura, secciones, combinar, reemplazar conservando formato, plantillas | `ops_docx.py` | — | `test_documents.py` (17) | Probado (auto) |
| 36 | Corte de Word por páginas físicas (resultado PDF) | `op_docx_pages` | LibreOffice | Revisado (requiere motor) | Requiere motor |
| 37 | Office→PDF, combinar heterogéneos en PDF, aislamiento y tiempo máximo | `engines.convert_with_office` | LibreOffice | `test_documents.py::test_office_conversion_when_available` (LibreOffice Linux) | Probado (auto) en Linux; Pendiente infra en Windows |
| 38 | Requisito exacto cuando falta Office sin romper PDF | `engines.office_engine_status` | — | `test_documents.py` (18) | Probado (auto) |
| 39 | Tablas PDF→XLSX/CSV con revisión | `pdf_tables` (pdfplumber) | — | Revisado | Revisado |
| 40 | OCR opcional | `engines.ocr_image_to_pdf` | Tesseract | Detección y mensaje revisados; motor no instalado | Requiere motor |
| 41 | Diseñador de etiquetas: mm, reglas, cuadrícula, zoom, guías, selección múltiple, alinear/distribuir, capas, bloqueo, deshacer, duplicar | `designer.js` | — | E2E (render y agregar código) | Probado (E2E); funciones avanzadas revisadas |
| 42 | Texto, campos variables, imágenes, líneas, rectángulos, QR, Code 128; desbordamiento | `labels/render.py`, `barcode.py` | — | `test_labels.py` (19, overflow) | Probado (auto) |
| 43 | Data Matrix / GS1 | No implementado | — | — | No incluido (declarado) |
| 44 | Tamaño físico exacto, DPI real, módulo y zona de silencio | `dots()`, módulos en puntos enteros | — | `test_labels.py` (mediabox exacto, ^PW) | Probado (auto) |
| 45 | Vincular a Excel/CSV, registros autorizados o valores solicitados; transformaciones seguras | `_records_from_source`, `resolve()` | — | `test_labels.py::test_transforms…`, E2E | Probado (auto/E2E) |
| 46 | Plantillas JSON versionadas: crear, editar, duplicar, importar/exportar, borrador, publicar | `LabelTemplate(Version)` | — | `test_labels.py::test_19` (revisión 409) | Probado (auto) |
| 47 | Vista previa con datos reales; PDF/SVG a escala; impresión por registro/selección/rango/lote con confirmación total | `print.html`, `printwizard.js` | — | `test_labels.py::test_print_api_requires_confirmed_total`, E2E | Probado (auto/E2E) |
| 48 | Ruta navegador (PDF tamaño exacto, instrucciones 100 %) | `to_pdf` | — | E2E | Probado (E2E); impresión física pendiente |
| 49 | Impresoras del servidor (cola Windows/CUPS), ZPL por red; registradas por admin; prueba de conexión; desactivadas hasta validar | `printing.py`, `Printer` | pywin32 (Windows), impresora | `test_labels.py` (21, no validada) con servidor TCP simulado | Probado (auto) con simulación; **Pendiente físico** |
| 50 | Estados honestos (generado/enviado/cola/desconocido/confirmado/fallido); sin reimpresión automática | `services.create_and_print`, `PrintEvent` | — | `test_labels.py` (21) | Probado (auto) |
| 51 | Consecutivos transaccionales sin duplicados; doble clic | `reserve_serials`, `idempotency_key` | — | `test_labels.py` (20, hilos concurrentes) | Probado (auto) |
| 52 | Reimpresión con permiso y motivo; trazabilidad completa | `api_reprint` | — | `test_labels.py::test_reprint…` | Probado (auto) |
| 53 | CAB u otras marcas | Ruta PDF con controlador; sin lenguaje nativo | Controlador del fabricante | — | Pendiente físico (documentado) |
| 54 | Kaizen: registro, flujo, tablero, PDCA, 5 porqués, vínculos, antes/después, ahorros aprobados, A3 | `apps/kaizen` | — | `kaizen/tests/test_kaizen.py` (22), E2E | Probado (auto/E2E) |
| 55 | Seguridad: CSRF, CSP, hash de contraseñas, sesiones, archivos privados, validación de cargas, macros, inyección CSV | `middleware.py`, `files.py`, exportadores | — | `test_security.py` | Probado (auto) |
| 56 | Auditoría, logs con ID de operación sin secretos | `audit()`, `OperationIdFilter` | — | `test_documents.py::test_invalid_ranges_and_protected` (contraseña no aparece) | Probado (auto) |
| 57 | Respaldo y restauración coherentes | `gpv_backup`, `gpv_restore` | — | `test_backup.py` (23) en SQLite y PostgreSQL | Probado (auto) |
| 58 | Trabajos persistentes, progreso, cancelación, recuperación, limpieza | `core/jobs.py`, `run_worker`, `cleanup_temp` | Proceso trabajador | Reportes/documentos vía cola en pruebas; recuperación revisada | Probado (auto) parcial |
| 59 | Diagnóstico de BD, carpetas, convertidores, colas | `diagnostics.py`, `gpv_diagnose` | — | E2E página diagnóstico; comando ejecutado | Probado (E2E) |
| 60 | Configuración dev/prod separada; demo no activo en producción | `gpvhub/settings` | — | `seed_demo` rechazado con GPV_ENV=prod; Waitress + collectstatic | Revisado |
| 61 | PostgreSQL para multiusuario | settings `GPV_DB_ENGINE` | PostgreSQL | Suite completa en PostgreSQL 16 | Probado (auto) |
| 62 | Generador 100 000 filas y escenario concurrente | `gen_perf_data`, `gpv_benchmark`, `tools/load_test.py` | — | Ver TEST_RESULTS.md | Probado (medido) |
| 63 | HTTPS, servicio Windows, IIS, LibreOffice Windows, capacidad corporativa | Documentado en DESPLIEGUE_INTERNO.md | Infraestructura TI | — | Pendiente infra |
