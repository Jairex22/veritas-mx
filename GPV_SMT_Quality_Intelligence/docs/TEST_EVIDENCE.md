# Evidencia de pruebas

Fecha de ejecución: 2026-11-04 · Entorno de desarrollo: Linux, Python 3.11.18 (sin acceso a la red de GPV).
Comando: `python -W error::DeprecationWarning -m unittest discover -s tests -t . -v`

**Resultado: 100 pruebas, 0 fallos, 0 errores.** Las advertencias de deprecación se trataron como errores, sin incidencias.

> Ninguna prueba se ejecutó contra FactoryLogix real. Los escenarios HTTP (200, vacío, 401, 403, 404, 429, 500/503 con reintento, timeout, conexión rechazada, DNS, JSON inválido, redirección, paginación) se probaron contra un servidor HTTP local falso (`tests/helpers.py`).

## Cobertura por requisito

| Requisito | Pruebas |
|---|---|
| Parser OData / JSON inválido / datos vacíos / nulls | `test_odata_core.ParserTests` |
| Metadatos (v4, v3, DOCTYPE, comparación) | `test_odata_core.MetadataTests` |
| Filtros, escape, inyección, tipos, límites | `test_odata_core.FilterTests` |
| HTTP 401/403/404/429/500, timeout, conexión interrumpida, DNS, política, credenciales, logs sin contraseña | `test_odata_client` |
| Defectos únicos, cierre, Closed≠PASS, historial incompleto, "False" no interpretado | `test_analytics.DefectTests` |
| Orden cronológico, zonas horarias mixtas, fechas nulas | `test_analytics.TimelineTests` |
| Seriales/operaciones repetidas, reproceso, bucle solo con flujo autorizado | `test_analytics.ReworkTests` |
| Caso Mirion W07632100028 (criterios de aceptación) | `test_traceability.MirionAcceptance` |
| Fallo parcial (QualityHistory) sin ocultar SMT, todos fallan = ERROR, vacío = NOT_FOUND, caché desactualizada tras timeout | `test_traceability.FailureModes` |
| Pulse, Quality, Rework en demo; fixture histórico fuera de Pulse | `test_traceability.ModulesDemo` |
| Caché: GUID vacío, deduplicación, historial mismo DefectID, demo/live separados | `test_storage_reports.CacheTests` |
| Configuración sin contraseñas, banderas de seguridad no editables | `test_storage_reports.ConfigTests` |
| Exportación CSV/XLSX/HTML, anti-fórmulas, XSS | `test_storage_reports.ReportTests` |
| Servidor: CSP, CSRF, Origin, Host (DNS rebinding), límites, traversal, reportes | `test_server_frontend.ServerTests` |
| Frontend: sin sinks DOM inseguros, sin scripts en línea, IDs y rutas API existentes, 9 secciones, sin etiqueta PASS | `test_server_frontend.FrontendStaticTests` |

## Prueba manual en navegador (Chromium headless, 1366×900 y 390×844)

Recorrido automatizado: Dashboard → escaneo `W07632100028` + Enter → Trazabilidad → Pulse (4 h) → Quality + "Calcular tiempos de cierre" → Rework (detalle de alerta) → `DEMO-QH-FAIL` → `DEMO-ERR-500` → Diagnóstico ($metadata) → Configuración → tema oscuro → descarga XLSX.
Resultado: 0 errores de consola / JavaScript; descarga `DEMO_GPV_Reporte_W07632100028.xlsx`; layout móvil sin desbordamiento horizontal.

Resultado observado del caso Mirion: 4 eventos SMT, 1 defecto único (3 entradas de historial), AOI Top ×2 marcado como operación repetida del mismo Identifier, SMT REPAIR, defecto Closed (cierre 15:23:50.020, AOI-3D-PC-L3, operador 40846), QA SMT posterior, resultado final **NO VERIFICABLE**, alertas R02, R03, R04, R05, R06, R08, R09.

## Salida completa

```
test_closed_without_closure_history (tests.test_analytics.DefectTests.test_closed_without_closure_history) ... ok
test_defect_id_case_insensitive (tests.test_analytics.DefectTests.test_defect_id_case_insensitive) ... ok
test_history_rows_never_counted_as_defects (tests.test_analytics.DefectTests.test_history_rows_never_counted_as_defects) ... ok
test_history_unavailable_marks_incomplete (tests.test_analytics.DefectTests.test_history_unavailable_marks_incomplete) ... ok
test_mirion_fod_counted_once (tests.test_analytics.DefectTests.test_mirion_fod_counted_once) ... ok
test_nulls_tolerated (tests.test_analytics.DefectTests.test_nulls_tolerated) ... ok
test_open_and_unknown (tests.test_analytics.DefectTests.test_open_and_unknown) ... ok
test_confirmed_loop_only_with_authorized_flow (tests.test_analytics.ReworkTests.test_confirmed_loop_only_with_authorized_flow) ... ok
test_duplicate_event (tests.test_analytics.ReworkTests.test_duplicate_event) ... ok
test_mirion_rules (tests.test_analytics.ReworkTests.test_mirion_rules) ... ok
test_no_alerts_for_clean_flow (tests.test_analytics.ReworkTests.test_no_alerts_for_clean_flow) ... ok
test_chronological_and_nulls_last (tests.test_analytics.TimelineTests.test_chronological_and_nulls_last) ... ok
test_defect_counted_once_in_timeline (tests.test_analytics.TimelineTests.test_defect_counted_once_in_timeline) ... ok
test_mixed_offsets_sorted_by_instant (tests.test_analytics.TimelineTests.test_mixed_offsets_sorted_by_instant) ... ok
test_401_not_retried (tests.test_odata_client.ClientTests.test_401_not_retried) ... ok
test_403_not_retried (tests.test_odata_client.ClientTests.test_403_not_retried) ... ok
test_404 (tests.test_odata_client.ClientTests.test_404) ... ok
test_429 (tests.test_odata_client.ClientTests.test_429) ... ok
test_500_retried_with_backoff_then_fails (tests.test_odata_client.ClientTests.test_500_retried_with_backoff_then_fails) ... Reintento 2/2 para SMT tras SERVER_ERROR (espera 0.0s)
ok
test_503_then_success (tests.test_odata_client.ClientTests.test_503_then_success) ... Reintento 2/2 para SMT tras SERVER_ERROR (espera 0.0s)
ok
test_basic_auth_header_sent_and_not_logged (tests.test_odata_client.ClientTests.test_basic_auth_header_sent_and_not_logged) ... ok
test_connection_refused (tests.test_odata_client.ClientTests.test_connection_refused) ... ok
test_dns_failure (tests.test_odata_client.ClientTests.test_dns_failure) ... ok
test_empty_is_distinct_from_error (tests.test_odata_client.ClientTests.test_empty_is_distinct_from_error) ... ok
test_entity_missing_in_metadata (tests.test_odata_client.ClientTests.test_entity_missing_in_metadata) ... ok
test_invalid_json_and_structure (tests.test_odata_client.ClientTests.test_invalid_json_and_structure) ... ok
test_metadata_failure_falls_back_and_marks_unverified (tests.test_odata_client.ClientTests.test_metadata_failure_falls_back_and_marks_unverified) ... ok
test_missing_credentials (tests.test_odata_client.ClientTests.test_missing_credentials) ... ok
test_no_auth_header_when_none (tests.test_odata_client.ClientTests.test_no_auth_header_when_none) ... ok
test_ok_with_rows (tests.test_odata_client.ClientTests.test_ok_with_rows) ... ok
test_pagination_foreign_origin_ignored (tests.test_odata_client.ClientTests.test_pagination_foreign_origin_ignored) ... ok
test_pagination_same_origin (tests.test_odata_client.ClientTests.test_pagination_same_origin) ... ok
test_policy_blocks (tests.test_odata_client.ClientTests.test_policy_blocks) ... ok
test_redirect_not_followed (tests.test_odata_client.ClientTests.test_redirect_not_followed) ... ok
test_results_emitted_for_audit (tests.test_odata_client.ClientTests.test_results_emitted_for_audit) ... ok
test_timeout_not_retried (tests.test_odata_client.ClientTests.test_timeout_not_retried) ... ok
test_control_chars_and_length (tests.test_odata_core.FilterTests.test_control_chars_and_length) ... ok
test_escape_quotes (tests.test_odata_core.FilterTests.test_escape_quotes) ... ok
test_field_must_exist_in_metadata (tests.test_odata_core.FilterTests.test_field_must_exist_in_metadata) ... ok
test_full_url_shape (tests.test_odata_core.FilterTests.test_full_url_shape) ... ok
test_in_operator_limited (tests.test_odata_core.FilterTests.test_in_operator_limited) ... ok
test_injection_attempt_stays_inside_literal (tests.test_odata_core.FilterTests.test_injection_attempt_stays_inside_literal) ... ok
test_top_bounds (tests.test_odata_core.FilterTests.test_top_bounds) ... ok
test_typed_literals (tests.test_odata_core.FilterTests.test_typed_literals) ... ok
test_unauthorized_field_entity_operator (tests.test_odata_core.FilterTests.test_unauthorized_field_entity_operator) ... ok
test_parse_fixture (tests.test_odata_core.MetadataTests.test_parse_fixture) ... ok
test_rejects_doctype_and_garbage (tests.test_odata_core.MetadataTests.test_rejects_doctype_and_garbage) ... ok
test_v3_detection (tests.test_odata_core.MetadataTests.test_v3_detection) ... ok
test_empty_value_is_valid (tests.test_odata_core.ParserTests.test_empty_value_is_valid) ... ok
test_invalid_json (tests.test_odata_core.ParserTests.test_invalid_json) ... ok
test_null_values_preserved (tests.test_odata_core.ParserTests.test_null_values_preserved) ... ok
test_unexpected_structures (tests.test_odata_core.ParserTests.test_unexpected_structures) ... ok
test_v2_results_and_next (tests.test_odata_core.ParserTests.test_v2_results_and_next) ... ok
test_v4_value (tests.test_odata_core.ParserTests.test_v4_value) ... ok
test_all_referenced_ids_exist (tests.test_server_frontend.FrontendStaticTests.test_all_referenced_ids_exist) ... ok
test_api_routes_used_exist (tests.test_server_frontend.FrontendStaticTests.test_api_routes_used_exist) ... ok
test_main_search_texts (tests.test_server_frontend.FrontendStaticTests.test_main_search_texts) ... ok
test_no_inline_scripts_or_handlers (tests.test_server_frontend.FrontendStaticTests.test_no_inline_scripts_or_handlers) ... ok
test_no_pass_label_in_ui (tests.test_server_frontend.FrontendStaticTests.test_no_pass_label_in_ui) ... ok
test_no_unsafe_dom_sinks (tests.test_server_frontend.FrontendStaticTests.test_no_unsafe_dom_sinks) ... ok
test_sidebar_has_nine_sections (tests.test_server_frontend.FrontendStaticTests.test_sidebar_has_nine_sections) ... ok
test_api_requires_csrf (tests.test_server_frontend.ServerTests.test_api_requires_csrf) ... ok
test_bad_input_400 (tests.test_server_frontend.ServerTests.test_bad_input_400) ... ok
test_body_limit (tests.test_server_frontend.ServerTests.test_body_limit) ... ok
test_config_cannot_enable_security_flags (tests.test_server_frontend.ServerTests.test_config_cannot_enable_security_flags) ... ok
test_diagnostics (tests.test_server_frontend.ServerTests.test_diagnostics) ... ok
test_dns_rebinding_host_rejected (tests.test_server_frontend.ServerTests.test_dns_rebinding_host_rejected) ... ok
test_foreign_origin_rejected (tests.test_server_frontend.ServerTests.test_foreign_origin_rejected) ... ok
test_index_has_csp_and_token (tests.test_server_frontend.ServerTests.test_index_has_csp_and_token) ... ok
test_report_download (tests.test_server_frontend.ServerTests.test_report_download) ... ok
test_static_and_traversal (tests.test_server_frontend.ServerTests.test_static_and_traversal) ... ok
test_status_and_trace (tests.test_server_frontend.ServerTests.test_status_and_trace) ... ok
test_dedup_between_windows (tests.test_storage_reports.CacheTests.test_dedup_between_windows) ... ok
test_demo_and_live_never_mixed (tests.test_storage_reports.CacheTests.test_demo_and_live_never_mixed) ... ok
test_empty_guid_not_used_as_key (tests.test_storage_reports.CacheTests.test_empty_guid_not_used_as_key) ... ok
test_file_database (tests.test_storage_reports.CacheTests.test_file_database) ... ok
test_history_same_defect_not_overwritten (tests.test_storage_reports.CacheTests.test_history_same_defect_not_overwritten) ... ok
test_example_config_loads (tests.test_storage_reports.ConfigTests.test_example_config_loads) ... ok
test_limits (tests.test_storage_reports.ConfigTests.test_limits) ... ok
test_password_in_config_rejected (tests.test_storage_reports.ConfigTests.test_password_in_config_rejected) ... ok
test_security_flags_not_editable (tests.test_storage_reports.ConfigTests.test_security_flags_not_editable) ... ok
test_sanitize (tests.test_storage_reports.LogSanitizeTests.test_sanitize) ... ok
test_csv (tests.test_storage_reports.ReportTests.test_csv) ... ok
test_html_escapes (tests.test_storage_reports.ReportTests.test_html_escapes) ... ok
test_xlsx_is_valid_ooxml (tests.test_storage_reports.ReportTests.test_xlsx_is_valid_ooxml) ... ok
test_all_sources_fail_is_error_not_empty (tests.test_traceability.FailureModes.test_all_sources_fail_is_error_not_empty) ... ok
test_empty_is_not_found (tests.test_traceability.FailureModes.test_empty_is_not_found) ... ok
test_invalid_identifier_rejected (tests.test_traceability.FailureModes.test_invalid_identifier_rejected) ... ok
test_quality_history_failure_does_not_hide_smt (tests.test_traceability.FailureModes.test_quality_history_failure_does_not_hide_smt) ... ok
test_timeout_uses_last_valid_cache_marked_stale (tests.test_traceability.FailureModes.test_timeout_uses_last_valid_cache_marked_stale) ... ok
test_fod_once_aoi_not_two_boards (tests.test_traceability.MirionAcceptance.test_fod_once_aoi_not_two_boards) ... ok
test_header (tests.test_traceability.MirionAcceptance.test_header) ... ok
test_merged_sources (tests.test_traceability.MirionAcceptance.test_merged_sources) ... ok
test_never_pass (tests.test_traceability.MirionAcceptance.test_never_pass) ... ok
test_repair_and_closed_shown (tests.test_traceability.MirionAcceptance.test_repair_and_closed_shown) ... ok
test_report_generated (tests.test_traceability.MirionAcceptance.test_report_generated) ... ok
test_pulse_excludes_historical_fixture (tests.test_traceability.ModulesDemo.test_pulse_excludes_historical_fixture) ... ok
test_pulse_filter_and_shift_errors (tests.test_traceability.ModulesDemo.test_pulse_filter_and_shift_errors) ... ok
test_quality_unique_defects (tests.test_traceability.ModulesDemo.test_quality_unique_defects) ... ok
test_rework_batch (tests.test_traceability.ModulesDemo.test_rework_batch) ... ok

----------------------------------------------------------------------
Ran 100 tests in 13.234s

OK
```
