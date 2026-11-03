# Pruebas y resultados (ejecutadas realmente)

## Versión 1.1.0 — Portal del turno, piloto SMT (2026-11-03)

Entorno: contenedor Linux x86_64, 4 vCPU Intel Xeon @ 2.30 GHz, 15 GB RAM. **No se ejecutó en
Windows** ni con personal de GPV. FactoryLogix **no** estuvo disponible: todas las pruebas de OData
usan el servicio **simulado** `tools/fake_odata_server.py` (OData v4 JSON, solo GET).

### Clasificación de la evidencia

| Categoría | Qué incluye |
|---|---|
| Simulado | Conector OData, sincronización, diagnóstico, lagunas, conciliación con eventos OData |
| Probado con muestras sintéticas | Mi turno, captura web, conteo, reportes, relevo, permisos, etiquetas (PDF), respaldo |
| Conectado a fuente real | **Nada** (pendiente de acceso de GPV) |
| Pendiente de entorno | Windows (INSTALAR/INICIAR.bat), FactoryLogix real, autenticación Windows integrada, impresora física, usuarios reales |

### Resultados

| Ejecución | Resultado |
|---|---|
| Suite automatizada, Python 3.13, SQLite | **121/121 OK** (72 existentes + 49 nuevas) |
| Suite automatizada, PostgreSQL 16 | **121/121 OK** |
| Suite en Python 3.11 y 3.12 | **121/121 OK** y **119 OK + 2 omitidas** (3.12 sin el lector opcional zxing-cpp) |
| E2E portal del turno `tools/e2e_shift.js`, escritorio | **17/17** (base nueva; repetido 3 veces sobre la misma base: 17/17) |
| E2E portal del turno, móvil 390×844 (incluye control de desbordamiento horizontal) | **17/17** |
| E2E general `tools/e2e_smoke.js` (escritorio + móvil) | **45/45** |
| Flujos por rol `tools/e2e_roles.js` escritorio / móvil | **19/19** / **19/19** |
| Recorrido de enlaces por rol `tools/e2e_crawl_roles.js` (operador, lector, supervisor, ingeniero, admin; 687 páginas) | **0 problemas** (sin 403 desde el menú, sin 500, sin errores de consola) |
| Errores 500 / trazas en registros del sitio y del servicio durante todas las corridas | **0** |
| Extracción limpia del ZIP, Python 3.12, `migrate`, `check`, `seed_demo`, sitio + servicio | Arranque correcto; estáticos 200; **E2E del portal 17/17** contra esa instalación |
| Actualización desde una base v1.0.1 con datos de demostración | `shift.0001_initial` aplicada; **44 tablas existentes con conteos idénticos** (solo crece el catálogo de permisos); páginas principales 200 |
| Interfaces de escucha | Sitio y servicio simulado solo en `127.0.0.1` (verificado en `/proc/net/tcp`) |

### Fallos encontrados y corregidos durante 1.1.0

| Fallo | Cómo se detectó | Corrección |
|---|---|---|
| Re-sincronizar OData creaba eventos repetidos (la clave externa no se guardaba) | `test_paging_and_repeated_sync_do_not_duplicate` | Se guarda la clave; restricción única activa |
| La búsqueda por clave externa no usaba índice en SQLite (sincronización O(n²)) | Medición de rendimiento | Índice `(conexión, clave externa)`; re-sincronización 1.78 s → 0.27 s |
| Formularios con varios botones perdían el valor del botón pulsado (p. ej. «Confirmar impresión física» quedaba como **fallido**) | E2E del portal (diagnóstico sin efecto) | Se conserva `name/value` del botón; paso E2E de confirmación física |
| Desbordamiento horizontal en móvil (estado de fuentes, vista previa de etiqueta de 420 px) | E2E móvil con medición de ancho | CSS/JS adaptable |
| Detalle de una orden mostraba registros de otra área y un enlace a un lote sin permiso | Recorrido por rol (lector) | Registros filtrados por área + prueba `OrderAreaTests` |
| En una instalación nueva el servicio generaba 21 borradores de la semana anterior al alta de la línea | Extracción limpia | Solo turnos posteriores al alta + `test_no_backfill_before_line_creation` |

### Criterios de aceptación 1–28

| # | Criterio | Evidencia | Estado |
|---|---|---|---|
| 1 | Arranque desde extracción limpia, estáticos, login, roles | Extracción limpia + E2E; `test_all_shift_pages_render_for_each_role` | Probado (Linux); Windows pendiente |
| 2 | Operador localiza su orden y la siguiente acción | `test_my_shift_*`, `test_operator_lands_on_my_shift_after_login…`, E2E | Probado (sin usuarios reales) |
| 3 | Fuente de ejemplo ingresa datos y actualiza la pantalla con trazabilidad | `test_ui_diagnose_then_enable_and_sync`, E2E (diagnóstico → sincronización → serie con historial) | Simulado |
| 4 | Repetido, doble clic, consulta solapada y reinicio no duplican | `test_paging_and_repeated_sync…`, `test_manual_capture_idempotent…`, `test_offline_json_resend…`, `test_drafts_generated_once…` | Probado |
| 5 | Reintento de prueba no es otra pieza; primera prueba conserva su significado | `test_retests_are_not_extra_pieces_and_fpy_uses_first_attempt` | Probado |
| 6 | Snapshot reemplaza su alcance | `test_snapshot_replaces_previous`; `ImportTests.test_04` | Probado |
| 7 | Interrupción conserva últimos datos y muestra retraso, nunca cero | `test_failure_keeps_last_data_backs_off_and_capture_still_works` | Simulado |
| 8 | 230/300 = 76.67 % agrupado | `MetricsTests.test_06` (capa común); cumplimiento del turno usa Σ/Σ | Probado |
| 9 | Reporte, PDF y exportación coinciden | `test_report_screen_pdf_and_excel_show_same_figures`; `MetricsTests.test_08` | Probado |
| 10 | Cruce de medianoche, datos tardíos y revisión sin borrar historia | `test_midnight_window`, `test_late_data_creates_new_revision` | Probado |
| 11 | Generación una vez por periodo con reintentos | `test_drafts_generated_once_by_process_even_after_restart`; `ScheduleTests.test_13` | Probado |
| 12 | Relevo conserva incidencias y separa recepción de resolución | `test_handover_receipt_does_not_close_incidents` | Probado |
| 13 | Aviso se asigna, atiende y verifica con permisos | `test_help_request_routing_dedupe_flow_and_verification`, E2E mantenimiento | Probado |
| 14 | Material sin movimiento ficticio de inventario | `test_material_request_is_not_inventory` | Probado |
| 15 | Instrucción vigente y lista según orden/operación | `test_instructions_only_approved_and_checklist_failure_creates_pending` | Probado |
| 16 | Escaneo, vista previa e impresión sin duplicar trabajos ni consecutivos | `test_label_from_context_once_and_scanner_guard`, E2E (Enter no imprime); `SerialConcurrencyTests.test_20` | Probado (PDF); impresora física pendiente |
| 17 | Borrador, error de sincronización y conflicto visibles y recuperables | Estado de fuente y `SyncRun` con error; borradores de reporte; `ConflictTests.test_10` | Probado |
| 18 | Permisos en backend, incluidos archivos y descargas | `test_role_adapted_views_and_server_side_permissions`, `test_station_of_other_area_is_rejected`, reporte PDF 403 a otra área, `SecurityTests` | Probado |
| 19 | Móvil y teclado | E2E móvil 17/17 y 19/19; Enter del escáner | Probado (Chromium) |
| 20 | Respaldo restaurado abre registros, archivos y plantillas | `test_23_backup_restore…`, `test_backup_restore_keeps_shift_portal_data` | Probado |
| 21 | OData distingue índice, metadata y permiso real a la entidad | `test_staged_diagnosis_distinguishes_index_metadata_and_entity_permission` | Simulado |
| 22 | Manual + OData del mismo hecho no suman dos veces; historial | `test_same_fact_manual_80_and_odata_80_is_80_not_160` (80, no 160), `EventRevision` | Probado |
| 23 | Dos lotes iguales no son duplicados; coincidencia ambigua a revisión | `test_two_independent_lots_are_160`, `test_ambiguous_equal_quantity_without_reference_goes_to_review` | Probado |
| 24 | Top/Bottom y paneles sin factor supuesto | `test_top_and_bottom_of_same_panel_not_double_counted`, `test_panels_need_confirmed_factor` | Probado |
| 25 | Captura web funciona con OData caído; cifras con aviso de antigüedad | `test_failure_keeps_last_data_backs_off_and_capture_still_works` | Simulado |
| 26 | Paginación y reintentos sin omitir ni duplicar | `test_paging_and_repeated_sync_do_not_duplicate` (5 páginas), `test_source_correction_creates_new_version` | Simulado |
| 27 | Apagado/reinicio recupera sincronización y reporte una sola vez, indicando lagunas no recuperables | `test_gap_after_computer_off_is_reported`, `test_drafts_generated_once…`, `test_service_lease_prevents_overlap` | Simulado |
| 28 | Ninguna escritura a FactoryLogix; ningún navegador recibe credenciales | `test_client_is_read_only_and_secrets_never_reach_browser_or_db`; el simulado registra solo GET | Probado |

### Rendimiento (datos sintéticos, `tools/perf_shift.py`, SQLite, un proceso)

| Medición | Resultado |
|---|---|
| Sincronización inicial de 20 000 eventos (40 páginas de 500) | 23.6 s (una sola vez; incluye el costo del servicio simulado) |
| Re-sincronización incremental con solape de 10 min (≈ 440 filas releídas, 0 nuevas) | 0.27 s |
| Mi turno / API de estado / pantalla del área / tablero / cierre con 10 000 eventos de conteo en el turno (10 órdenes) | mediana 0.41–0.46 s, p95 ≤ 0.51 s por solicitud |
| Igual con 1 000 eventos de conteo | ≈ 0.10 s |

Con refresco de 60 s, un equipo atiende holgadamente las pantallas de una línea piloto. Concurrencia:
ver la tabla de carga siguiente. Estas cifras **no** son de FactoryLogix real (su latencia y volumen son
desconocidos); el intervalo de 60 s debe ajustarse tras medir el origen real.

| Carga concurrente (`tools/load_test.py --turno`) | Resultado |
|---|---|
| 10 usuarios simultáneos × 20 solicitudes (Mi turno, API de estado, notificaciones, Mi trabajo, pantalla del área), `runserver` + SQLite, datos de demostración | 200 OK, **0 errores**, 18.3 solicitudes/s, p50 389 ms, p95 1 096 ms |

En el uso real cada pantalla consulta cada 60 s, es decir, 10 pantallas ≈ 0.2 solicitudes/s.

### Limitaciones de esta evidencia

* Sin Windows, sin FactoryLogix, sin impresora física, sin personal de GPV: los resultados del piloto
  con operadores **no existen** todavía (guion en `PILOTO_SMT.md`).
* OData v2/v3 probado solo a nivel de formato (`ODataFormatTests`).

---

## Versión 1.0.1 — auditoría por roles y correcciones (2026-11-02)

Entorno: contenedor Linux x86_64, 4 vCPU, 15 GB RAM. No se ejecutó en Windows.

### Fallos reproducidos y corregidos

| # | Fallo | Cómo se reprodujo | Estado |
|---|---|---|---|
| F1 | Menú con secciones prohibidas para operador/lector (403) | Recorrido de enlaces por rol (`tools/e2e_crawl_roles.js`) | Corregido + prueba |
| F2 | «Lote #N» de la trazabilidad → 403 para quien no creó el lote | Recorrido por rol (analista) | Corregido + prueba |
| F3 | Incidencias de operador no notificaban a nadie; sin bandeja | Flujo supervisor «resolver incidencia» | Corregido + prueba + flujo E2E |
| F4 | Instructivo Windows: `<usuario>` literal y doble carpeta al extraer | Reporte del usuario (PowerShell) | Corregido (instructivo, INSTALAR/INICIAR.bat); **no ejecutado en Windows** |
| F5 | Supervisor de otra área podía revertir importaciones ajenas | Prueba de regresión de F2 | Corregido + prueba |
| F6 | Trabajos de etiquetas y datasets sin control de área | Revisión del mismo patrón | Corregido + prueba |
| F7 | Lotes con columna Área propia inaccesibles para esas áreas | Recorrido por rol tras corregir F2 | Corregido + prueba |
| F8 | Hoja de cálculo: lo tecleado se perdía si llegaba el recálculo | Escritura a velocidad humana (120 ms/tecla) | Corregido + E2E |
| F9 | Detalle de reporte («Abrir resultado») siempre en error 500 | Recorrido por rol sobre datos con reportes | Corregido + prueba + compilación de todas las plantillas |

Las pruebas de regresión `apps/core/tests/test_role_flows.py` se ejecutaron contra el código v1.0.0:
**6 fallos y 2 errores** (detectan los defectos); contra v1.0.1: **todas OK**.

### Resultados

| Ejecución | Resultado |
|---|---|
| Suite automatizada, repositorio, Python 3.13, SQLite | **72/72 OK** |
| Suite automatizada, PostgreSQL 16 | **72/72 OK** |
| Extracción limpia del ZIP v1.0.1, Python 3.12, solo núcleo, **con los datos de una instalación v1.0.0 copiados** | `migrate`: sin migraciones nuevas; datos conservados (232 registros, 24 órdenes, 7 lotes, 14 archivos, todos legibles); `check` y `gpv_diagnose` sin errores; **72 OK, 2 omitidas** (lector opcional zxing-cpp) |
| Flujos por rol `tools/e2e_roles.js` (escritorio) sobre esa instalación | **19/19**, repetido 3 veces seguidas |
| Flujos por rol en móvil (390×844) | **19/19** |
| Recorrido de enlaces por rol `tools/e2e_crawl_roles.js` (operador, lector, supervisor, analista, admin; 415 páginas) | **0 problemas** (sin 403 desde el menú, sin 500, sin errores de consola) |
| E2E general `tools/e2e_smoke.js` (escritorio + móvil) | **45/45** |
| Errores 500 en el log del servidor durante todas las corridas | **0** |
| Carga, 10 usuarios × 20 solicitudes (runserver, SQLite) | 200 OK, 0 errores, 7.9 rps, p50 993 ms, p95 2593 ms |

Flujos cubiertos: **operador** (confirmar comunicado, capturar avance en orden asignada, registrar
incidencia, proponer Kaizen, imprimir etiqueta PDF, consultar dashboard y documentos); **supervisor**
(publicar comunicado dirigido, resolver incidencia desde la bandeja, cambiar meta con motivo, aprobar
Kaizen, programar reporte, revertir importación, reimprimir etiqueta con motivo); **analista** (importar
CSV con fila inválida por el asistente, crear y guardar dashboard, generar reporte de calidad, hoja con
fórmula escrita a velocidad humana + guardar + exportar, extraer páginas PDF, diseñar etiqueta).

### Pendiente en 1.0.1

* Las mejoras específicas del «prompt de corrección y mejoras» **no se recibieron** (el adjunto era el ZIP
  v1.0.0 idéntico, SHA-256 `e556e5f3…`); se implementarán al recibir su texto.
* `INSTALAR.bat` / `INICIAR.bat` y los comandos de PowerShell no se ejecutaron en Windows (sin equipo Windows).
* Lo pendiente de 1.0.0 sigue vigente (impresoras físicas, infraestructura corporativa).

---

## Versión 1.0.0

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
