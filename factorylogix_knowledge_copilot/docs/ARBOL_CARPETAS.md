# Árbol de carpetas

> Generado por `scripts/generate_docs.py`.

```text
factorylogix_knowledge_copilot/
├── .streamlit/
│   └── config.toml
├── config/
│   ├── eval_set.yaml
│   ├── odata_entities.yaml
│   ├── rules.yaml
│   └── settings.yaml
├── connectors/
│   ├── __init__.py
│   ├── base.py
│   ├── odata.py
│   └── simulator.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── errors.py
│   ├── logging_setup.py
│   ├── text.py
│   └── utils.py
├── data/
├── database/
│   ├── __init__.py
│   ├── connection.py
│   └── schema.sql
├── demo_data/
│   ├── documents/
│   │   ├── DEMO-EXP-011_impresora_antigua.md
│   │   ├── DEMO-FAQ-013_preguntas_frecuentes.csv
│   │   ├── DEMO-KB-003_defectos_repair.md
│   │   ├── DEMO-KB-007_odata.html
│   │   ├── DEMO-KB-010_reintentos_ict_kb.md
│   │   ├── DEMO-KB-012_cambio_turno.md
│   │   ├── DEMO-MAN-005_genealogia_wip.docx
│   │   ├── DEMO-MAN-014_production_quick_reference.pdf
│   │   ├── DEMO-PROC-001_work_orders.md
│   │   ├── DEMO-PROC-006_escalamiento.md
│   │   ├── DEMO-RES-008_correccion_genealogia.md
│   │   ├── DEMO-REV-015_npi_borrador.md
│   │   ├── DEMO-WI-002_certificaciones.md
│   │   ├── DEMO-WI-004_etiquetas_shipping.md
│   │   └── DEMO-WI-009_reintentos_ict.md
│   └── manifest.yaml
├── docs/
│   ├── capturas/
│   │   ├── 01_login.png
│   │   ├── 03_answer_operator.png
│   │   ├── 04_conflict.png
│   │   ├── 05_no_evidence.png
│   │   └── 06_mes_urgent.png
│   ├── ARBOL_CARPETAS.md
│   ├── ARQUITECTURA.md
│   ├── CHECKLIST_SEGURIDAD.md
│   ├── DEMO_PILOTO_PRODUCCION.md
│   ├── DICCIONARIO_DATOS.md
│   ├── ESQUEMA_BASE_DATOS.md
│   ├── GUIA_ACTUALIZAR_REGLAS.md
│   ├── GUIA_AGREGAR_CONOCIMIENTO.md
│   ├── GUIA_GOBIERNO_DATOS.md
│   ├── GUIA_ODATA_SEGURO.md
│   ├── INVENTARIO_DEPENDENCIAS_LICENCIAS.md
│   ├── MANUAL_ADMINISTRADOR.md
│   ├── MANUAL_INSTALACION.md
│   ├── MANUAL_USUARIO.md
│   ├── MATRIZ_RBAC.md
│   ├── MODELO_AMENAZAS.md
│   ├── PLAN_RESPALDO_RESTAURACION.md
│   ├── POLITICA_RETENCION.md
│   └── REPORTE_PRUEBAS.md
├── governance/
│   ├── __init__.py
│   ├── lifecycle.py
│   └── policies.py
├── ingestion/
│   ├── __init__.py
│   ├── chunking.py
│   ├── cleaning.py
│   ├── extractors.py
│   └── pipeline.py
├── knowledge_base/
│   └── README.md
├── logs/
├── models/
│   ├── __init__.py
│   └── domain.py
├── pages/
│   ├── __init__.py
│   ├── analytics.py
│   ├── audit.py
│   ├── catalog.py
│   ├── chat.py
│   ├── evaluations.py
│   ├── feedback_review.py
│   ├── governance.py
│   ├── health.py
│   ├── incidents.py
│   ├── settings.py
│   ├── sources.py
│   ├── training_center.py
│   └── users.py
├── rag/
│   ├── __init__.py
│   ├── answer_builder.py
│   ├── confidence.py
│   ├── conflicts.py
│   ├── embeddings.py
│   ├── engine.py
│   ├── lexical.py
│   ├── llm.py
│   ├── query.py
│   └── retriever.py
├── reports/
├── repositories/
│   ├── __init__.py
│   ├── audit.py
│   ├── base.py
│   ├── chunks.py
│   ├── documents.py
│   ├── operations.py
│   └── users.py
├── schemas/
│   ├── __init__.py
│   └── validation.py
├── scripts/
│   ├── __init__.py
│   ├── build_demo_assets.py
│   ├── build_release.py
│   ├── check_env.py
│   ├── generate_docs.py
│   ├── launch.py
│   ├── PREPARAR_WHEELS_OFFLINE.bat
│   ├── process_utils.py
│   ├── reset_admin.py
│   ├── run_checks.py
│   └── stop.py
├── security/
│   ├── __init__.py
│   ├── auth.py
│   ├── file_validation.py
│   ├── injection.py
│   ├── passwords.py
│   ├── rate_limit.py
│   ├── rbac.py
│   └── sanitize.py
├── sentiment/
│   ├── __init__.py
│   └── analyzer.py
├── services/
│   ├── __init__.py
│   ├── analytics_service.py
│   ├── audit_helper.py
│   ├── backup_service.py
│   ├── chat_service.py
│   ├── connector_service.py
│   ├── container.py
│   ├── demo_loader.py
│   ├── evaluation_service.py
│   ├── export_service.py
│   ├── feedback_service.py
│   ├── health_service.py
│   ├── incident_service.py
│   ├── knowledge_service.py
│   ├── settings_service.py
│   └── user_service.py
├── tests/
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_auth_users_audit.py
│   │   ├── test_chat_service.py
│   │   ├── test_incidents_feedback_eval.py
│   │   ├── test_knowledge_workflow.py
│   │   └── test_startup_and_ui.py
│   ├── rag/
│   │   ├── __init__.py
│   │   └── test_rag_evaluation.py
│   ├── security/
│   │   ├── __init__.py
│   │   ├── test_codebase_policy.py
│   │   └── test_security_controls.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_connectors.py
│   │   ├── test_core_text_and_query.py
│   │   ├── test_ingestion.py
│   │   ├── test_llm_and_export.py
│   │   ├── test_passwords_ratelimit_lifecycle.py
│   │   ├── test_rag_components.py
│   │   └── test_sentiment.py
│   ├── __init__.py
│   └── conftest.py
├── ui/
│   ├── __init__.py
│   ├── auth_view.py
│   ├── components.py
│   ├── i18n.py
│   ├── state.py
│   └── theme.py
├── .env.example
├── .gitattributes
├── .gitignore
├── app.py
├── DETENER_WINDOWS.bat
├── INICIAR_RED_INTERNA_WINDOWS.bat
├── INICIAR_WINDOWS.bat
├── INSTALAR_WINDOWS.bat
├── pyproject.toml
├── README.md
├── requirements-dev.txt
├── requirements-optional.txt
└── requirements.txt
```
