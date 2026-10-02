# Diccionario de datos

Fechas de evento en ISO-8601 UTC (`AAAA-MM-DDTHH:MM:SS+00:00`); fechas de vigencia en `AAAA-MM-DD`.

## documents — catálogo de documentos (identidad y metadatos actuales)

| Campo | Tipo | Descripción |
|---|---|---|
| id | TEXT PK | ID único (`doc-…`) |
| doc_code | TEXT UNIQUE | Código legible (ej. `WI-ICT-001`). Prefijo `DEMO-` para datos demo |
| title / description | TEXT | Nombre y descripción |
| source_type | TEXT | Procedure, Work Instruction, Official Manual, Knowledge Base, FAQ, Approved Q&A |
| owner / approver | TEXT | Propietario y aprobador designado |
| area | TEXT | Área responsable |
| customer, product, line, process, station | TEXT | Ámbito de aplicación (vacío = todos) |
| fl_module | TEXT | Operations, Production, Analytics, NPI, xTend, Quality, Shipping, General |
| classification | TEXT | Public, Internal, Confidential, Restricted |
| retention_policy | TEXT | Clave de `governance.retention_policies` |
| tags, language | TEXT | Etiquetas (coma) e idioma (es/en) |
| is_demo / is_active | INTEGER | Marca DEMO / activo para recuperación |
| published_version_id | TEXT | Versión publicada vigente |
| created_by, created_at, updated_at | TEXT | Trazabilidad |
| deleted_at, deleted_reason | TEXT | Lápida de eliminación autorizada |

## document_versions — versiones

| Campo | Tipo | Descripción |
|---|---|---|
| id | TEXT PK | `ver-…` |
| document_id | TEXT FK | Documento |
| version_no / version_label | INTEGER / TEXT | Número y etiqueta (`1.0`) |
| status | TEXT | Draft, Under Review, Approved, Rejected, Expired, Archived |
| content_hash | TEXT | SHA-256 del texto normalizado (duplicados) |
| file_name, stored_path, file_kind, size_bytes, page_count | — | Archivo original (ruta relativa segura) |
| extracted_text | TEXT | Texto extraído (con marcas de página) |
| injection_flags / injection_ack_by | TEXT | Hallazgos de prompt injection y quién los confirmó |
| duplicate_of | TEXT | Código del duplicado exacto detectado |
| effective_date, review_date, expiration_date | TEXT | Vigencia |
| change_note | TEXT | Nota de cambio |
| created_by/at, submitted_by/at, decided_by/at, decision_reason | TEXT | Flujo de aprobación |
| ever_approved | INTEGER | Habilita rollback |
| published_at, archived_at | TEXT | Publicación/archivo |

## chunks — fragmentos recuperables

| Campo | Descripción |
|---|---|
| id, version_id, document_id, chunk_index | Linaje |
| section, page | Sección (“Documento > Tema”) y página |
| text, char_count | Texto del fragmento |
| embedding, embedding_model | Vector float32 y modelo que lo generó |
| injection_flag | Fragmento con instrucciones sospechosas |

`chunks_fts` (FTS5): `chunk_id`, `title`, `section`, `text` con tokenizador `unicode61 remove_diacritics 2`.

## Registros de gobierno

| Tabla | Campos clave |
|---|---|
| metadata_changes | document_id, field, old_value, new_value, changed_by, changed_at, reason |
| approvals | version_id, document_id, action (submit, approve, reject, publish, superseded, rollback, expire, archive), actor, at, reason |

## Operación

| Tabla | Campos clave |
|---|---|
| query_log | user_id, role, correlation_id, question (redactada), language, answered, confidence, confidence_level, latency_ms, mode, conflict, topic, filters, sentiment_label, sentiment_expires_at |
| answer_sources | query_id, chunk_id, version_id, document_id, rank, score (linaje respuesta → fuente) |
| feedback | query_id, user_id, rating (up/down), comment, is_correction, question, original_answer, proposed_answer, status (closed, pending_review, accepted_to_qa, dismissed), reviewed_by/at, review_note |
| qa_pairs | question, answer, fl_module, classification, language, status, created_by, decided_by/at, document_id (publicada), source_feedback_id |
| incidents | code, created_by(_role), question, answer, work_order, serial_number, assembly, station, operation, error_message, attachment_path, sources, preliminary_diagnosis, urgency, suggested_area, status, notes |
| evaluation_runs | started_at, finished_at, run_by, summary (JSON), details (JSON) |
| system_errors | ts, component, error_type, message (redactado), correlation_id |
| app_settings | key, value (JSON), updated_by, updated_at |

## Seguridad

| Tabla | Campos clave |
|---|---|
| users | username (único, sin mayúsculas/minúsculas), display_name, role, password_hash (scrypt), must_change_password, is_active, failed_attempts, locked_until, auth_source, is_demo |
| sessions | user_id, started_at, last_seen_at, ended_at, end_reason |
| audit_log | seq, id, ts, username, role, action, object_type, object_id, result, reason, correlation_id, details, prev_hash, hash |
