# Resultados de pruebas automatizadas

* Fecha de ejecución: 2026-11-03T22:14Z
* Intérprete: Python 3.14.6 (Linux, entorno de desarrollo). También ejecutadas con Python 3.13 y 3.11: OK.
* Comando: `py -m unittest discover -s tests -v` (aquí con `-W error::DeprecationWarning`)
* Alcance: código completo contra **simulador local** y servidores HTTP de prueba en 127.0.0.1.
* **No incluye pruebas de integración con FactoryLogix real** (servidor no accesible desde el entorno de desarrollo).

Además se realizó una prueba de interfaz en Chromium (Playwright): consulta, caché, tendencia con periodo anterior, exportación XLSX/CSV/PDF, pantallas Tendencias/Reportes/Estado de conexión y vista móvil 390 px, sin errores de consola ni violaciones CSP. El XLSX generado se abrió y convirtió correctamente con LibreOffice.

| Requisito | Archivo de prueba |
|---|---|
| 1-2 Metadata y detección de campos | test_metadata.py |
| 3 Validación de filtros | test_security.py, test_service.py |
| 4-5 Caché y expiración | test_cache.py |
| 6-10 Límites, concurrencia, HTTP, timeouts, circuit breaker | test_odata_client.py |
| 11 Cálculos | test_analytics.py |
| 12-13 CSV y reportes | test_reports.py |
| 14 Seguridad | test_security.py |
| 15 Modo DEMO | test_demo.py |
| Otra entidad / descargas masivas / refresco / concurrencia / no inventar / sin bucles / sin consulta sin filtros | test_odata_client.py, test_service.py, test_analytics.py |

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
test_examples_are_marked_simulated (test_demo.DemoModeTests.test_examples_are_marked_simulated) ... ok
test_full_flow (test_demo.DemoModeTests.test_full_flow) ... ok
test_generator_deterministic_and_not_future (test_demo.DemoModeTests.test_generator_deterministic_and_not_future) ... ok
test_separate_database_file (test_demo.DemoModeTests.test_separate_database_file) ... ok
test_simulator_rejects_unsupported_options (test_demo.DemoModeTests.test_simulator_rejects_unsupported_options) ... ok
test_starts_ready_without_network (test_demo.DemoModeTests.test_starts_ready_without_network) ... ok
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
test_no_credentials_in_url (test_security.ConfigSecurityTests.test_no_credentials_in_url) ... ok
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

----------------------------------------------------------------------
Ran 114 tests in 5.861s

OK
```
