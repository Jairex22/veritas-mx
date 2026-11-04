# Resultados de pruebas automatizadas — v1.1.3

* Fecha de ejecución: 2026-11-04T16:55Z
* Intérprete: Python 3.14.6 con `-W error::DeprecationWarning`; también Python 3.11: OK. (Entorno Linux de desarrollo; no se ejecutó en Windows.)
* Comando: `py -m unittest discover -s tests -v`
* Alcance: servidor OData **simulado** (`demo_source.DemoTransport` y variantes con fallas 401/500/timeout/desconexión/filtros rechazados) y servidores HTTP de prueba en 127.0.0.1.
* **Autenticación de Windows (SSPI):** la capa `sspi_auth.py` llama a `Secur32.dll` por ctypes y **solo puede ejecutarse en Windows**; en CI (Linux) no se ejecuta. Lo que sí se probó: el intercambio HTTP del handshake (401→token→200) sobre una conexión keep-alive con un proveedor de tokens simulado (`test_sspi.py`), y un flujo extremo a extremo (metadata + pruebas + entidad + ingesta de 6 registros) a través de `SspiHttpTransport` con proveedor simulado contra un servidor local que exige el handshake.
* **Observación real en GPV (04/11/2026, v1.1.0):** `$metadata` respondió 200 sin credenciales; `ProductivityOverTime` respondió 401. En v1.1.1 se retiró la autenticación (consultas anónimas) y se reprodujo ese escenario con un servidor local (200 en `$metadata`, 401 `Negotiate`/`NTLM` en la entidad): 2 solicitudes en total, ninguna con encabezado de autenticación, mensaje con los esquemas solicitados y espera de 10 min.
* **Sin pruebas de integración con datos reales de la entidad.** Verificación manual adicional: `py app.py --live` contra `10.62.54.10:6065` desde el entorno de desarrollo → 1 intento a `$metadata`, timeout de 15 s, espera de 300 s, advertencia visible en el monitor; una segunda instancia fue rechazada por el lock.
* Prueba de interfaz en Chromium (Playwright): Monitor con actualización sin recarga de página (1 navegación en 30+ s), Consulta histórica local con exportación XLSX, Tendencias local, Estado de conexión; ancho móvil 390 px sin desplazamiento horizontal; sin errores de consola ni de CSP. Con el hilo real del recolector (modo DEMO) el segundo ciclo se ejecutó solo, exactamente 300 s después del primero (48 registros nuevos, 2 sin cambio, sin duplicados).

| Requisito v1.1 | Prueba |
|---|---|
| Validación al inicio, 1 consulta por ciclo | test_collector: test_startup_validation_then_one_query_per_cycle |
| Filtro temporal y $top siempre presentes, sin nextLink | test_every_data_query_is_time_filtered_and_bounded |
| Sin duplicados + historial de lecturas | test_dedup_and_reading_history |
| Recuperación de historial sin paginación | test_catch_up_without_pagination, test_trend_not_computed_from_unsynced_hours, test_local_history_does_not_flag_unsynced_hours |
| Backoff, datos conservados, sin bucles | test_backoff_keeps_data_and_does_not_loop, test_circuit_breaker_stops_requests, test_auth_error_backs_off_longer_without_probes, test_server_down_at_startup_no_probe_loop |
| Bloqueo sin filtro de fecha validado | test_blocked_when_date_filter_fails |
| Usuarios no generan consultas | test_users_never_trigger_odata |
| Recolector único | LockTests.test_single_instance |
| 401 en la entidad con `$metadata` anónimo | WindowsAuthScenarioTests, test_repeated_auth_headers_kept |
| Handshake SSPI (parseo de reto, header, reuso de conexión, límite de saltos, redirect/tamaño) | test_sspi.py |
| Credenciales explícitas: holder en memoria, identidad al cliente SSPI, API set/clear, no persiste/log | test_security.py, test_collector.py |
| Acumulado vs intervalo | test_live_metrics: SemanticsTests |
| Sin datos recientes, incrementos, hora de producción vs consulta, dimensiones solo si existen | test_live_metrics: MonitorTests |

```
test_compare (test_analytics.AnalyticsTests.test_compare) ... ok
test_day_and_shift_interval (test_analytics.AnalyticsTests.test_day_and_shift_interval) ... ok
test_drop_detection_excludes_in_progress (test_analytics.AnalyticsTests.test_drop_detection_excludes_in_progress) ... ok
test_drop_needs_minimum_buckets (test_analytics.AnalyticsTests.test_drop_needs_minimum_buckets) ... ok
test_empty_period (test_analytics.AnalyticsTests.test_empty_period) ... ok
test_invalid_records_excluded_and_reported (test_analytics.AnalyticsTests.test_invalid_records_excluded_and_reported) ... ok
test_legacy_date_format (test_analytics.AnalyticsTests.test_legacy_date_format) ... ok
test_no_invented_kpis (test_analytics.AnalyticsTests.test_no_invented_kpis) ... ok
test_no_quantity_field_means_no_production_metric (test_analytics.AnalyticsTests.test_no_quantity_field_means_no_production_metric) ... ok
test_parse_number (test_analytics.AnalyticsTests.test_parse_number) ... ok
test_totals_and_buckets (test_analytics.AnalyticsTests.test_totals_and_buckets) ... ok
test_trend (test_analytics.AnalyticsTests.test_trend) ... ok
test_truncated_is_partial (test_analytics.AnalyticsTests.test_truncated_is_partial) ... ok
test_demo_and_live_never_mix (test_cache.DatabaseCacheTests.test_demo_and_live_never_mix) ... ok
test_expiration (test_cache.DatabaseCacheTests.test_expiration) ... ok
test_no_credentials_columns (test_cache.DatabaseCacheTests.test_no_credentials_columns) ... ok
test_only_three_snapshots_per_signature (test_cache.DatabaseCacheTests.test_only_three_snapshots_per_signature) ... ok
test_retention_cleanup (test_cache.DatabaseCacheTests.test_retention_cleanup) ... ok
test_signature_stable (test_cache.DatabaseCacheTests.test_signature_stable) ... ok
test_size_limit_trims_oldest (test_cache.DatabaseCacheTests.test_size_limit_trims_oldest) ... ok
test_store_and_read (test_cache.DatabaseCacheTests.test_store_and_read) ... ok
test_expired_cache_triggers_one_request (test_cache.ServiceCacheTests.test_expired_cache_triggers_one_request) ... ok
test_force_refresh_respects_min_interval (test_cache.ServiceCacheTests.test_force_refresh_respects_min_interval) ... ok
test_interval_change_does_not_requery (test_cache.ServiceCacheTests.test_interval_change_does_not_requery) ... ok
test_last_query_never_contacts_server (test_cache.ServiceCacheTests.test_last_query_never_contacts_server) ... ok
test_second_query_served_from_cache_for_any_session (test_cache.ServiceCacheTests.test_second_query_served_from_cache_for_any_session) ... ok
test_auth_error_backs_off_longer_without_probes (test_collector.CollectorTests.test_auth_error_backs_off_longer_without_probes) ... ok
test_auto_mapping_is_flagged (test_collector.CollectorTests.test_auto_mapping_is_flagged) ... ok
test_backfill_floor_and_gaps (test_collector.CollectorTests.test_backfill_floor_and_gaps) ... ok
test_backoff_keeps_data_and_does_not_loop (test_collector.CollectorTests.test_backoff_keeps_data_and_does_not_loop) ... ok
test_blocked_when_date_filter_fails (test_collector.CollectorTests.test_blocked_when_date_filter_fails) ... ok
test_catch_up_without_pagination (test_collector.CollectorTests.test_catch_up_without_pagination) ... ok
test_circuit_breaker_stops_requests (test_collector.CollectorTests.test_circuit_breaker_stops_requests) ... ok
test_config_mapping_not_overridden (test_collector.CollectorTests.test_config_mapping_not_overridden) ... ok
test_dedup_and_reading_history (test_collector.CollectorTests.test_dedup_and_reading_history) ... ok
test_every_data_query_is_time_filtered_and_bounded (test_collector.CollectorTests.test_every_data_query_is_time_filtered_and_bounded) ... ok
test_local_history_does_not_flag_unsynced_hours (test_collector.CollectorTests.test_local_history_does_not_flag_unsynced_hours) ... ok
test_server_down_at_startup_no_probe_loop (test_collector.CollectorTests.test_server_down_at_startup_no_probe_loop) ... ok
test_startup_validation_then_one_query_per_cycle (test_collector.CollectorTests.test_startup_validation_then_one_query_per_cycle) ... ok
test_state_persists_across_restart (test_collector.CollectorTests.test_state_persists_across_restart) ... ok
test_trend_not_computed_from_unsynced_hours (test_collector.CollectorTests.test_trend_not_computed_from_unsynced_hours) ... ok
test_users_never_trigger_odata (test_collector.CollectorTests.test_users_never_trigger_odata) ... ok
test_missing_fields (test_collector.CredentialsTests.test_missing_fields) ... ok
test_rejected_without_sspi (test_collector.CredentialsTests.test_rejected_without_sspi) ... ok
test_set_and_clear (test_collector.CredentialsTests.test_set_and_clear) ... ok
test_single_instance (test_collector.LockTests.test_single_instance) ... ok
test_auth_hint_for_anonymous_transport (test_collector.WindowsAuthScenarioTests.test_auth_hint_for_anonymous_transport) ... ok
test_metadata_ok_entity_401 (test_collector.WindowsAuthScenarioTests.test_metadata_ok_entity_401) ... ok
test_examples_are_marked_simulated (test_demo.DemoModeTests.test_examples_are_marked_simulated) ... ok
test_full_flow (test_demo.DemoModeTests.test_full_flow) ... ok
test_generator_deterministic_and_not_future (test_demo.DemoModeTests.test_generator_deterministic_and_not_future) ... ok
test_separate_database_file (test_demo.DemoModeTests.test_separate_database_file) ... ok
test_simulator_rejects_unsupported_options (test_demo.DemoModeTests.test_simulator_rejects_unsupported_options) ... ok
test_starts_ready_without_network (test_demo.DemoModeTests.test_starts_ready_without_network) ... ok
test_cumulative_today_uses_baseline_from_yesterday (test_live_metrics.MonitorTests.test_cumulative_today_uses_baseline_from_yesterday) ... ok
test_dimensions_only_when_mapped (test_live_metrics.MonitorTests.test_dimensions_only_when_mapped) ... ok
test_increment_between_readings (test_live_metrics.MonitorTests.test_increment_between_readings) ... ok
test_no_data_at_all (test_live_metrics.MonitorTests.test_no_data_at_all) ... ok
test_no_recent_data (test_live_metrics.MonitorTests.test_no_recent_data) ... ok
test_production_time_vs_query_time (test_live_metrics.MonitorTests.test_production_time_vs_query_time) ... ok
test_syncing_state (test_live_metrics.MonitorTests.test_syncing_state) ... ok
test_trend_last_complete_hours (test_live_metrics.MonitorTests.test_trend_last_complete_hours) ... ok
test_undetermined_semantics_produces_no_units (test_live_metrics.MonitorTests.test_undetermined_semantics_produces_no_units) ... ok
test_units_today_and_lines (test_live_metrics.MonitorTests.test_units_today_and_lines) ... ok
test_cumulative_detected (test_live_metrics.SemanticsTests.test_cumulative_detected) ... ok
test_cumulative_groups_are_independent (test_live_metrics.SemanticsTests.test_cumulative_groups_are_independent) ... ok
test_cumulative_increments_with_reset_and_no_baseline (test_live_metrics.SemanticsTests.test_cumulative_increments_with_reset_and_no_baseline) ... ok
test_insufficient_or_conflicting (test_live_metrics.SemanticsTests.test_insufficient_or_conflicting) ... ok
test_interval_detected (test_live_metrics.SemanticsTests.test_interval_detected) ... ok
test_interval_increment_is_quantity (test_live_metrics.SemanticsTests.test_interval_increment_is_quantity) ... ok
test_units_between_marks_partial (test_live_metrics.SemanticsTests.test_units_between_marks_partial) ... ok
test_best_guess (test_metadata.FieldDetectionTests.test_best_guess) ... ok
test_missing_role_reported_no_disponible (test_metadata.FieldDetectionTests.test_missing_role_reported_no_disponible) ... ok
test_suggestions_only_use_existing_compatible_fields (test_metadata.FieldDetectionTests.test_suggestions_only_use_existing_compatible_fields) ... ok
test_validate_mapping_rejects_duplicates (test_metadata.FieldDetectionTests.test_validate_mapping_rejects_duplicates) ... ok
test_validate_mapping_rejects_invented_or_wrong_type (test_metadata.FieldDetectionTests.test_validate_mapping_rejects_invented_or_wrong_type) ... ok
test_capability_annotations_are_announced_only (test_metadata.MetadataParsingTests.test_capability_annotations_are_announced_only) ... ok
test_forbidden_entity (test_metadata.MetadataParsingTests.test_forbidden_entity) ... ok
test_invalid_and_unsafe_xml (test_metadata.MetadataParsingTests.test_invalid_and_unsafe_xml) ... ok
test_missing_entity_set (test_metadata.MetadataParsingTests.test_missing_entity_set) ... ok
test_only_productivity_entity_is_read (test_metadata.MetadataParsingTests.test_only_productivity_entity_is_read) ... ok
test_save_and_load (test_metadata.MetadataParsingTests.test_save_and_load) ... ok
test_v2_with_inheritance (test_metadata.MetadataParsingTests.test_v2_with_inheritance) ... ok
test_v4_entity_set_and_properties (test_metadata.MetadataParsingTests.test_v4_entity_set_and_properties) ... ok
test_400_does_not_open_breaker (test_odata_client.CircuitBreakerTests.test_400_does_not_open_breaker) ... ok
test_429_retry_after_opens_immediately (test_odata_client.CircuitBreakerTests.test_429_retry_after_opens_immediately) ... ok
test_breaker_unit (test_odata_client.CircuitBreakerTests.test_breaker_unit) ... ok
test_failures_open_breaker_and_stop_requests (test_odata_client.CircuitBreakerTests.test_failures_open_breaker_and_stop_requests) ... ok
test_concurrency_config_is_capped_to_one (test_odata_client.ConcurrencyAndLimitsTests.test_concurrency_config_is_capped_to_one) ... ok
test_parallel_burst_sends_one (test_odata_client.ConcurrencyAndLimitsTests.test_parallel_burst_sends_one) ... ok
test_single_active_request (test_odata_client.ConcurrencyAndLimitsTests.test_single_active_request) ... ok
test_spacing_and_budgets (test_odata_client.ConcurrencyAndLimitsTests.test_spacing_and_budgets) ... ok
test_http_statuses (test_odata_client.ErrorHandlingTests.test_http_statuses) ... ok
test_next_link_never_followed (test_odata_client.ErrorHandlingTests.test_next_link_never_followed) ... ok
test_no_retries (test_odata_client.ErrorHandlingTests.test_no_retries) ... ok
test_operator_message_for_connection_error (test_odata_client.ErrorHandlingTests.test_operator_message_for_connection_error) ... ok
test_top_ignored_by_server_is_truncated (test_odata_client.ErrorHandlingTests.test_top_ignored_by_server_is_truncated) ... ok
test_transport_failures (test_odata_client.ErrorHandlingTests.test_transport_failures) ... ok
test_formats (test_odata_client.PayloadTests.test_formats) ... ok
test_invalid (test_odata_client.PayloadTests.test_invalid) ... ok
test_metadata_takes_no_options (test_odata_client.UrlBuildingTests.test_metadata_takes_no_options) ... ok
test_only_allowed_resources (test_odata_client.UrlBuildingTests.test_only_allowed_resources) ... ok
test_only_get_and_no_other_entity_requested (test_odata_client.UrlBuildingTests.test_only_get_and_no_other_entity_requested) ... ok
test_rejects_injection_in_parts (test_odata_client.UrlBuildingTests.test_rejects_injection_in_parts) ... ok
test_top_mandatory_and_bounded (test_odata_client.UrlBuildingTests.test_top_mandatory_and_bounded) ... ok
test_connection_refused (test_odata_client.UrllibTransportTests.test_connection_refused) ... ok
test_ok (test_odata_client.UrllibTransportTests.test_ok) ... ok
test_redirect_blocked (test_odata_client.UrllibTransportTests.test_redirect_blocked) ... ok
test_repeated_auth_headers_kept (test_odata_client.UrllibTransportTests.test_repeated_auth_headers_kept) ... ok
test_size_limit (test_odata_client.UrllibTransportTests.test_size_limit) ... ok
test_timeout (test_odata_client.UrllibTransportTests.test_timeout) ... ok
test_csv (test_reports.ReportTests.test_csv) ... ok
test_csv_formula_injection (test_reports.ReportTests.test_csv_formula_injection) ... ok
test_filenames (test_reports.ReportTests.test_filenames) ... ok
test_list_and_delete (test_reports.ReportTests.test_list_and_delete) ... ok
test_report_requires_query (test_reports.ReportTests.test_report_requires_query) ... ok
test_snapshot_contents (test_reports.ReportTests.test_snapshot_contents) ... ok
test_viewed_source_cannot_be_forged_for_old_data (test_reports.ReportTests.test_viewed_source_cannot_be_forged_for_old_data) ... ok
test_xlsx_is_valid_workbook (test_reports.ReportTests.test_xlsx_is_valid_workbook) ... ok
test_auto_refresh_default_off (test_security.ConfigSecurityTests.test_auto_refresh_default_off) ... ok
test_credentials_never_persisted_or_logged (test_security.ConfigSecurityTests.test_credentials_never_persisted_or_logged) ... ok
test_invalid_auth_mode_rejected (test_security.ConfigSecurityTests.test_invalid_auth_mode_rejected) ... ok
test_no_credentials_in_url (test_security.ConfigSecurityTests.test_no_credentials_in_url) ... ok
test_no_stored_credentials (test_security.ConfigSecurityTests.test_no_stored_credentials) ... ok
test_only_authorized_entity (test_security.ConfigSecurityTests.test_only_authorized_entity) ... ok
test_only_localhost_by_default (test_security.ConfigSecurityTests.test_only_localhost_by_default) ... ok
test_source_has_no_eval_or_shell (test_security.ConfigSecurityTests.test_source_has_no_eval_or_shell) ... ok
test_templates_have_no_inline_script (test_security.ConfigSecurityTests.test_templates_have_no_inline_script) ... ok
test_body_size_limit_and_methods (test_security.HttpLayerTests.test_body_size_limit_and_methods) ... ok
test_no_arbitrary_odata_from_browser (test_security.HttpLayerTests.test_no_arbitrary_odata_from_browser) ... ok
test_post_requires_csrf_header (test_security.HttpLayerTests.test_post_requires_csrf_header) ... ok
test_rejects_foreign_host (test_security.HttpLayerTests.test_rejects_foreign_host) ... ok
test_security_headers_and_cookie (test_security.HttpLayerTests.test_security_headers_and_cookie) ... ok
test_static_traversal_http (test_security.HttpLayerTests.test_static_traversal_http) ... ok
test_dates (test_security.InputValidationTests.test_dates) ... ok
test_filter_values (test_security.InputValidationTests.test_filter_values) ... ok
test_host_and_origin (test_security.InputValidationTests.test_host_and_origin) ... ok
test_literals (test_security.InputValidationTests.test_literals) ... ok
test_property_names (test_security.InputValidationTests.test_property_names) ... ok
test_redaction (test_security.InputValidationTests.test_redaction) ... ok
test_spreadsheet_injection (test_security.InputValidationTests.test_spreadsheet_injection) ... ok
test_static_traversal (test_security.InputValidationTests.test_static_traversal) ... ok
test_failed_filters_block_and_never_query_unfiltered (test_service.LiveModeBlockingTests.test_failed_filters_block_and_never_query_unfiltered) ... ok
test_filter_ignored_by_server_marked_failed (test_service.LiveModeBlockingTests.test_filter_ignored_by_server_marked_failed) ... ok
test_incompatible_metadata (test_service.LiveModeBlockingTests.test_incompatible_metadata) ... ok
test_live_starts_without_network_and_blocks (test_service.LiveModeBlockingTests.test_live_starts_without_network_and_blocks) ... ok
test_mapping_rejects_nonexistent_fields (test_service.LiveModeBlockingTests.test_mapping_rejects_nonexistent_fields) ... ok
test_metadata_connectivity_is_not_functional_validity (test_service.LiveModeBlockingTests.test_metadata_connectivity_is_not_functional_validity) ... ok
test_probe_and_metadata_rate_limits (test_service.LiveModeBlockingTests.test_probe_and_metadata_rate_limits) ... ok
test_probe_requests_are_bounded (test_service.LiveModeBlockingTests.test_probe_requests_are_bounded) ... ok
test_query_failure_does_not_fallback_and_no_loop (test_service.LiveModeBlockingTests.test_query_failure_does_not_fallback_and_no_loop) ... ok
test_schema_change_invalidates_probes (test_service.LiveModeBlockingTests.test_schema_change_invalidates_probes) ... ok
test_unverified_filter_not_accepted (test_service.LiveModeBlockingTests.test_unverified_filter_not_accepted) ... ok
test_auto_refresh_disabled (test_service.QueryValidationTests.test_auto_refresh_disabled) ... ok
test_max_records_limit_and_partial_flag (test_service.QueryValidationTests.test_max_records_limit_and_partial_flag) ... ok
test_rules (test_service.QueryValidationTests.test_rules) ... ok
test_stored_data_labelled_not_live (test_service.QueryValidationTests.test_stored_data_labelled_not_live) ... ok
test_make_client_off_windows_raises (test_sspi.AvailabilityTests.test_make_client_off_windows_raises) ... ok
test_extract (test_sspi.ChallengeParsingTests.test_extract) ... ok
test_account_rejected_returns_401 (test_sspi.SspiTransportTests.test_account_rejected_returns_401) ... ok
test_handshake_succeeds_and_reuses_one_connection (test_sspi.SspiTransportTests.test_handshake_succeeds_and_reuses_one_connection) ... ok
test_redirect_blocked (test_sspi.SspiTransportTests.test_redirect_blocked) ... ok
test_size_limit (test_sspi.SspiTransportTests.test_size_limit) ... ok
test_sspi_error_becomes_connection_error (test_sspi.SspiTransportTests.test_sspi_error_becomes_connection_error) ... ok

----------------------------------------------------------------------
Ran 164 tests in 13.530s

OK
```
