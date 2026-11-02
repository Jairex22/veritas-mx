# Resultados de pruebas (ejecutadas realmente)

Fecha: 2026-11-02 · Entorno de construcción: contenedor Linux x86_64 (4 vCPU Intel Xeon 2.8 GHz,
15 GB RAM). **No** se ejecutó en Windows: la compatibilidad Windows se verificó por disponibilidad de
ruedas binarias y por diseño (rutas, comandos sin PowerShell). Ver «Pendiente» al final.

## 1. Pruebas automatizadas (unitarias, integración y flujos de usuario)

Comando: `python manage.py test` (perfil `test`).

| Ejecución | Python | Base de datos | Dependencias | Resultado |
|---|---|---|---|---|
| Repositorio | 3.13.18 | SQLite (archivo) | núcleo + opcionales | **64 pruebas OK** |
| Repositorio | 3.13.18 | PostgreSQL 16 | núcleo + opcionales + psycopg 3.2.13 | **64 pruebas OK** |
| Entorno nuevo desde requirements | 3.11.18 | SQLite | núcleo + opcionales | **64 pruebas OK** |
| **Extracción limpia del ZIP** | 3.12.3 | SQLite | solo núcleo (`requirements.txt`) | **64 OK, 2 omitidas** (decodificación con lector opcional zxing-cpp no instalado) |

Las pruebas verifican resultados independientes (texto extraído del PDF, celdas del XLSX, códigos
decodificados por zxing-cpp, archivos reconstruidos, estados en base de datos), no solo valores de retorno.

Detalle (ejecución repositorio, SQLite):

| App | Prueba | Resultado |
|---|---|---|
| comms | test_11_publish_receive_ack.test_11_publish_receive_ack | ok |
| comms | test_comments_and_incidents_on_order.test_comments_and_incidents_on_order | ok |
| core | test_12_operator_cannot_change_permissions.test_12_operator_cannot_change_permissions | ok |
| core | test_12_operator_cannot_download_foreign_file.test_12_operator_cannot_download_foreign_file | ok |
| core | test_configurable_matrix.test_configurable_matrix | ok |
| core | test_csv_injection_neutralised.test_csv_injection_neutralised | ok |
| core | test_operator_only_captures_assigned_orders.test_operator_only_captures_assigned_orders | ok |
| core | test_security_headers_and_csrf.test_security_headers_and_csrf | ok |
| core | test_upload_validation.test_upload_validation | ok |
| documents | test_16_csv_split_preserves_header_quotes_newlines.test_16_csv_split_preserves_header_quotes_newlines | ok |
| documents | test_dedupe_and_clean.test_dedupe_and_clean | ok |
| documents | test_xlsx_extract_warns_broken_refs_and_rename_updates.test_xlsx_extract_warns_broken_refs_and_rename_updates | ok |
| documents | test_17_sections_combine_and_unsupported.test_17_sections_combine_and_unsupported | ok |
| documents | test_18_missing_office_reports_requirement_pdf_still_works.test_18_missing_office_reports_requirement_pdf_still_works | ok |
| documents | test_office_conversion_when_available.test_office_conversion_when_available | ok |
| documents | test_14_split_duplicate_rotate.test_14_split_duplicate_rotate | ok |
| documents | test_invalid_ranges_and_protected.test_invalid_ranges_and_protected | ok |
| documents | test_other_pdf_tools.test_other_pdf_tools | ok |
| documents | test_15_extract_duplicate_reorder_keep_relations.test_15_extract_duplicate_reorder_keep_relations | ok |
| documents | test_merge_preserves_masters.test_merge_preserves_masters | ok |
| documents | test_concurrent_thumbnails_do_not_crash.test_concurrent_thumbnails_do_not_crash | ok |
| kaizen | test_22_complete_and_report.test_22_complete_and_report | ok |
| labels | test_19_edit_bind_export_decode.test_19_edit_bind_export_decode | ok |
| labels | test_overflow_reported_not_deformed.test_overflow_reported_not_deformed | ok |
| labels | test_traceability_and_identification_templates_decode.test_traceability_and_identification_templates_decode | ok |
| labels | test_transforms_and_zpl_escaping.test_transforms_and_zpl_escaping | ok |
| labels | test_20_double_click_same_key_one_job.test_20_double_click_same_key_one_job | ok |
| labels | test_21_connection_failure_and_ambiguous_send.test_21_connection_failure_and_ambiguous_send | ok |
| labels | test_direct_printing_disabled_until_validated.test_direct_printing_disabled_until_validated | ok |
| labels | test_print_api_requires_confirmed_total.test_print_api_requires_confirmed_total | ok |
| labels | test_reprint_requires_permission_and_reason.test_reprint_requires_permission_and_reason | ok |
| production | test_01_xlsx_multisheet_and_spanish_csv.test_01_xlsx_multisheet_and_spanish_csv | ok |
| production | test_02_different_headers_same_schema_and_invalid_date_row.test_02_different_headers_same_schema_and_invalid_date_row | ok |
| production | test_03_reimport_same_file_does_not_duplicate.test_03_reimport_same_file_does_not_duplicate | ok |
| production | test_04_snapshot_replaces_not_sums.test_04_snapshot_replaces_not_sums | ok |
| production | test_05_serials_keep_leading_zeros_and_long_digits.test_05_serials_keep_leading_zeros_and_long_digits | ok |
| production | test_ambiguous_dates_require_choice.test_ambiguous_dates_require_choice | ok |
| production | test_area_permission_enforced_on_import.test_area_permission_enforced_on_import | ok |
| production | test_failure_mid_import_is_compensated.test_failure_mid_import_is_compensated | ok |
| production | test_formula_without_cached_value_is_computed_or_reported.test_formula_without_cached_value_is_computed_or_reported | ok |
| production | test_revert_keeps_later_changes.test_revert_keeps_later_changes | ok |
| production | test_06_grouped_compliance_is_ratio_of_sums.test_06_grouped_compliance_is_ratio_of_sums | ok |
| production | test_06b_excess_does_not_cancel_shortfall.test_06b_excess_does_not_cancel_shortfall | ok |
| production | test_07_not_calculable_and_insufficient.test_07_not_calculable_and_insufficient | ok |
| production | test_07b_fpy_uses_first_attempt_only.test_07b_fpy_uses_first_attempt_only | ok |
| production | test_07c_mixed_units_not_summed.test_07c_mixed_units_not_summed | ok |
| production | test_08_table_dashboard_pdf_excel_match.test_08_table_dashboard_pdf_excel_match | ok |
| production | test_area_isolation_in_metrics.test_area_isolation_in_metrics | ok |
| reports | test_13_runs_once_even_with_retries.test_13_runs_once_even_with_retries | ok |
| reports | test_all_formats_and_templates_generate.test_all_formats_and_templates_generate | ok |
| reports | test_missed_occurrences_collapse_to_one.test_missed_occurrences_collapse_to_one | ok |
| reports | test_next_occurrence_in_mexico_city.test_next_occurrence_in_mexico_city | ok |
| sheets | test_10_concurrent_edit_conflict.test_10_concurrent_edit_conflict | ok |
| sheets | test_protected_columns_server_side.test_protected_columns_server_side | ok |
| sheets | test_09_copy_and_structure_adjust_references.test_09_copy_and_structure_adjust_references | ok |
| sheets | test_09_errors_cycles_div0_unknown.test_09_errors_cycles_div0_unknown | ok |
| sheets | test_09_no_code_execution.test_09_no_code_execution | ok |
| sheets | test_09_supported_functions.test_09_supported_functions | ok |
| sheets | test_pivot.test_pivot | ok |
| sheets | test_server_matches_python_engine_for_reports.test_server_matches_python_engine_for_reports | ok |
| sheets | test_xlsx_roundtrip_types_and_warnings.test_xlsx_roundtrip_types_and_warnings | ok |
| core | test_23_backup_restore_and_open_files.test_23_backup_restore_and_open_files | ok |
| labels | test_20_concurrent_serials_unique.test_20_concurrent_serials_unique | ok |
| reports | test_two_schedulers_same_occurrence.test_two_schedulers_same_occurrence | ok |

### Correspondencia con los criterios de aceptación

| Criterio | Prueba |
|---|---|
| 1 XLSX varias hojas y CSV español/separadores/comillas | production · ImportTests.test_01 |
| 2 Encabezados distintos y fecha inválida en su fila exacta (fila 3) | ImportTests.test_02 |
| 3 Reimportar sin duplicar | ImportTests.test_03 |
| 4 Snapshot acumulado sin sumar (70, no 110) | ImportTests.test_04 |
| 5 Seriales con ceros y >15 dígitos | ImportTests.test_05 |
| 6 230/300 = 76.67 %, pendiente 70 | MetricsTests.test_06, test_06b |
| 7 «No calculable» y «Datos insuficientes» | MetricsTests.test_07, 07b, 07c |
| 8 Tabla = dashboard = PDF = Excel | MetricsTests.test_08 |
| 9 Fórmulas, ciclos, #DIV/0!, desconocidas | FormulaTests.* |
| 10 Conflicto de edición sin pérdida | ConflictTests.test_10 |
| 11 Comunicado recibido y confirmado | AnnouncementTests.test_11 |
| 12 Operador no cambia permisos ni descarga ajeno | SecurityTests.test_12_* |
| 13 Reporte programado una vez con reintentos | ScheduleTests.test_13, ConcurrentSchedulerTests |
| 14 PDF [1,3] y [2,4,5]; duplicar y rotar | PdfTests.test_14 |
| 15 PPTX extraer/duplicar/reordenar con imágenes y gráficos | PptxTests.test_15 |
| 16 CSV con encabezados, comillas y saltos de línea | CsvXlsxTests.test_16 |
| 17 DOCX secciones/combinar y detección de cambios | DocxTests.test_17 |
| 18 Requisito cuando falta Office; PDF sigue funcionando | OfficeMissingTests.test_18 |
| 19 Etiqueta: editar, vincular, tamaño exacto, decodificar | LabelDesignTests.test_19 (+ plantillas de trazabilidad e identificación) |
| 20 Consecutivos concurrentes y doble clic | SerialConcurrencyTests.test_20, PrintingTests.test_20 |
| 21 Falla de conexión y resultado ambiguo sin «Impreso» | PrintingTests.test_21 (servidores TCP simulados) |
| 22 Kaizen completo y reporte A3 | KaizenFlowTests.test_22 |
| 23 Restaurar respaldo y abrir archivos | BackupRestoreTests.test_23 (SQLite y PostgreSQL) |
| 24 Flujos en escritorio y móvil | E2E (sección 2) |

## 2. Prueba de navegador (E2E)

Herramienta: `tools/e2e_smoke.js` (Playwright + Chromium, solo desarrollo). Servidor: extracción
limpia del ZIP con `runserver`, datos `seed_demo`. Viewports 1366×860 y 390×844.
Falla ante errores de consola, recursos que no cargan (CSS/JS/imágenes), HTTP 5xx, imágenes rotas o
desbordamiento horizontal.

Resultado: **45/45 verificaciones correctas** (login, 14 páginas, clic en barra filtra dashboard,
generar reporte PDF+XLSX, editar hoja con fórmula y guardar, cortar PDF, diseñador de etiquetas
renderiza y agrega código, imprimir por navegador con confirmación, nueva mejora Kaizen, menú móvil),
en escritorio y móvil.

## 3. Compatibilidad de instalación en Windows

`pip download --only-binary=:all: --platform win_amd64 --python-version {3.11,3.12,3.13}` de
`requirements.txt` + `requirements-optional.txt`: **24 ruedas para cada versión**, sin necesidad de
compilar. Instalación real (Linux) desde cero con Python 3.11 y 3.12: correcta.

## 4. Perfil de producción

`GPV_ENV=prod`: `migrate`, `collectstatic`, `check --deploy` (solo avisos esperables al probar por HTTP
sin certificados: HSTS, redirección SSL y cookies seguras, que se activan con `.env` detrás de HTTPS),
Waitress 3.0.2 sirviendo login (200), CSS (200 text/css), redirección a login (302), página 404 propia,
cabeceras CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`. `seed_demo` se rechaza en prod.

## 5. Desempeño (medido, no certificado)

Generador reproducible: `manage.py gen_perf_data --rows 100000` (semilla 2026, 2 000 órdenes, 20 líneas).
Medición: `manage.py gpv_benchmark --rows 100000 --confirmar` (un proceso, base vacía).

| Etapa (100 000 filas) | SQLite | PostgreSQL 16 (local) |
|---|---|---|
| Analizar archivo | 2.37 s | 1.78 s |
| Validar (sin escribir) | 5.72 s | 5.05 s |
| Importar (revalida + escribe por bloques de 2 000) | 35.57 s | 36.55 s |
| `kpi_summary` (2 000 órdenes) | 0.27 s | 0.36 s |
| `order_rows` | 0.15 s | 0.51 s |
| Serie por día / por línea | 0.05 / 0.15 s | 0.05 / 0.05 s |
| Memoria máxima del proceso (SQLite) | 420 MB | — |

Concurrencia: `tools/load_test.py --users 10 --requests 20` contra `runserver` (desarrollo, SQLite,
datos demo), mezcla de inicio, plan, API del dashboard, notificaciones y registros:

| Ejecución | Solicitudes OK | Errores | rps | Media | p50 | p95 | Máx |
|---|---|---|---|---|---|---|---|
| Repositorio | 200 | 0 | 10.1 | 857 ms | 834 ms | 2042 ms | 2236 ms |
| Extracción limpia | 200 | 0 | 9.2 | 928 ms | 895 ms | 2301 ms | 2475 ms |

Cuellos de botella observados: `runserver` (un proceso, GIL) y la escritura única de SQLite; la
importación revalida todas las filas antes de escribir (por seguridad) y escribe registros con
imágenes previas para la reversión. **Estos números no certifican capacidad para cientos de usuarios.**
Repita en el servidor con Waitress + PostgreSQL.

## 6. Defectos encontrados y corregidos durante la validación

| Defecto | Detectado por | Corrección |
|---|---|---|
| El servidor terminaba con SIGSEGV al pedir miniaturas PDF en paralelo (PDFium no es seguro entre hilos) | E2E | Candado global `PDFIUM_LOCK`; prueba de regresión con 24 hilos |
| `form.dataset` ocultado por un campo llamado `dataset` (impresión de etiquetas) | E2E | Lectura de `dataset` vía `HTMLElement.prototype` (`GPV.ds`) |
| `SET TRANSACTION ISOLATION LEVEL` dentro de transacción abierta | Suite en PostgreSQL | Aislamiento solo en la transacción externa |
| Restauración: perfiles duplicados al cargar usuarios | Suite en PostgreSQL | La señal ignora `raw` (loaddata) |
| Dimensiones de texto/códigos rotados intercambiadas | Prueba de plantillas | Geometría local sin intercambio |
| Campos de texto nulos en importación (NOT NULL) | `seed_demo` | Normalización a cadena vacía |
| Lote fallido por filas con error quedaba bloqueado | Prueba de humo | Si no se aplicó nada vuelve a «Validado» |
| Fechas DD/MM inequívocas por columna marcadas como ambiguas | Prueba de humo | Evidencia por columna (valor >12) |
| Numeración de listas por estilo no detectada al combinar DOCX | Prueba 17 | Detección de estilos con numeración |
| Empaquetador excluía `tools/e2e_smoke.js` | Validación de extracción | Filtro solo para capturas `.png` |

## 7. Revisado manualmente (sin prueba automatizada completa)

Constructor de dashboards (UI), campos calculados y unión (UI), proyección, extracción de tablas PDF,
diálogos de formato condicional/validación/tabla dinámica de la hoja, alineación/distribución/capas del
diseñador, diagnóstico, capturas de pantalla de dashboard, plan, diseñador, Kaizen (escritorio y móvil).

## 8. Pendiente (no ejecutado aquí)

* **Impresora física**: tamaño, alineación, lectura con escáner, ZPL real, colas Windows/CUPS reales
  (ver `GUIA_VALIDACION_ETIQUETAS.md`). Los envíos se probaron con servidores TCP simulados.
* **Infraestructura corporativa**: Windows Server/IIS/HTTPS, servicio de Windows, LibreOffice en
  Windows (la conversión se probó con LibreOffice en Linux), Tesseract, carga con cientos de usuarios,
  PostgreSQL corporativo.
* Ejecución en Windows 10/11 con Edge (Chromium sí se probó).
