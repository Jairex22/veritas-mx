# A. Arquitectura propuesta — GPV FactoryLogix Command Center v1.0

## Principios

1. **Servicio web centralizado.** Un solo servicio Python (FastAPI + Uvicorn) aprobado por TI; los usuarios
   acceden con cualquier navegador corporativo. No se instala nada en las estaciones.
2. **Sin compilación en equipos restringidos.** El frontend son archivos estáticos (HTML + CSS + JavaScript
   ES modules) servidos por el mismo backend. No requiere npm, npx, Node, Docker ni CDN externos.
3. **Sólo lectura por defecto.** Ninguna ruta de código escribe en FactoryLogix. Las escrituras exigen un
   ejecutor real registrado, que en v1.0 **no existe** (ver `docs/INTEGRATIONS.md`).
4. **Veracidad.** Toda respuesta incluye la procedencia de los datos (`source.kind`, `source.synthetic`). En
   modo REAL sin conexión, la API responde 503 y la UI muestra "Sin fuente de datos" — nunca valores sustitutos.
5. **Separación DEMO / REAL** en tiempo de arranque (`GPV_MODE`). El modo no se puede cambiar desde el navegador.

## Diagrama de componentes

```
 Navegador corporativo (Edge/Chrome)
   │  HTTPS (cookie HttpOnly + cabecera X-CSRF-Token)
   ▼
┌──────────────────────────── Servicio GPV Command Center (Windows Server) ───────────────────────────┐
│ Middleware: correlación (X-Correlation-ID) · cabeceras de seguridad (CSP) · bitácora de accesos      │
│                                                                                                       │
│ API (backend/app/api)                                                                                 │
│  auth · search/units/panels · diagnostics · metrics · operations · packing · labels · connectors · audit│
│        │                     │               │              │                                         │
│ Servicios (backend/app/services)                                                                     │
│  DiagnosticsEngine   compute_metrics   OperationsService ──► Ejecutor DEMO (memoria)                  │
│                                         │  token HMAC · idempotencia · versión de estado              │
│                                         └─► Registro de ejecutores REALES = { } (vacío en v1.0)       │
│  LabelService (separado de producción)  AuditService (cadena SHA-256)                                 │
│        │                                                                                              │
│ Fuentes de datos (backend/app/data) — interfaz ProductionDataSource (sólo lectura)                    │
│  DemoDataSource │ ODataDataSource (mapeo verificado) │ AuxCsvDataSource │ UnavailableDataSource       │
│        │                     │                              │                                         │
│ Conectores (backend/app/connectors): OData · xTend (alcance) · FactoryLogixAPI (alcance) · Archivos   │
│                                                                                                       │
│ BD propia SQLite (var/gpv_command_center.db): sesiones · auditoría · accesos · idempotencia · impresión│
│ Logs JSON rotativos (var/logs/app.log)                                                                │
└───────────────────────────────────────────────────────────────────────────────────────────────────────┘
        │ GET OData ($metadata, EntitySets mapeados)          │ lectura de archivos
        ▼                                                     ▼
  FactoryLogix (OData / xTend / API)                   Carpeta de exportaciones CSV/XML
```

## Capas

| Capa | Ubicación | Responsabilidad |
|------|-----------|-----------------|
| Configuración | `backend/app/settings.py`, `.env`, `config/*.json` | Modo, URLs, credenciales (sólo servidor), mapeos |
| Autenticación | `backend/app/core/security.py` | Sesiones server-side (token SHA-256 en BD), roles, permisos, CSRF |
| Auditoría | `backend/app/services/audit.py` | Registro encadenado por hash; verificación de integridad |
| Conectores | `backend/app/connectors/` | Pruebas de conexión, diagnóstico HTTP, descubrimiento de capacidades |
| Fuentes de datos | `backend/app/data/` | Modelo de dominio común; adaptadores DEMO / OData / CSV |
| Diagnóstico | `backend/app/services/diagnostics.py` | 8 reglas de rework con hechos, hipótesis, confianza y riesgo |
| Operaciones | `backend/app/services/operations.py` | Catálogo, validación de flujo, prepare/execute, guardas de producción |
| Etiquetas | `backend/app/services/labels.py` | Impresoras, plantillas ZPL, previsualización, control de reimpresión |
| Métricas | `backend/app/services/metrics.py` | KPIs con definición formal |
| API | `backend/app/api/` | Rutas FastAPI, validación de entrada (Pydantic) |
| Frontend | `frontend/` | SPA sin build: `app.js`, `ui.js`, `charts.js`, `pages/*.js` |

## Flujo de una operación controlada

```
UI ──POST /prepare──► rol? acción disponible en este modo? parámetros válidos?
                      lee estado previo ─► valida flujo de proceso ─► audita (READY/BLOCKED)
   ◄── validaciones + token HMAC{acción, usuario, hash(params), versiones, exp 180 s, modo}
UI: modal de confirmación explícita (checkbox obligatorio)
UI ──POST /execute {params, token, idempotency_key, confirm:true}──►
      verifica token/usuario/params/modo ─► idempotencia (clave única; repetición = misma respuesta)
      bloqueo + compara versión de estado (409 si cambió) ─► re-valida flujo
      ejecuta (DEMO: simulador; REAL: NO DISPONIBLE) ─► comprobación posterior ─► audita
   ◄── estado previo/posterior, comprobaciones, respuesta del servidor (marcada SIMULADO), id auditoría
```

## Guardas contra escrituras accidentales en producción

* `OperationsService.real_executors` está vacío; `_ensure_available` responde 501 en REAL.
* `_run` lanza `ProductionWriteBlocked` si la fuente no es `DemoDataSource` sintética en modo DEMO.
* El módulo de operaciones no importa clientes de red ni SQL de escritura salvo la tabla propia
  `idempotency` (prueba estática `test_operations_module_has_no_network_or_sql_write_code`).
* Las pruebas `tests/test_demo_isolation.py` bloquean sockets/HTTP durante operaciones DEMO.
* El login DEMO se desactiva automáticamente en modo REAL.
* Acciones destructivas (p. ej. Scrap) están deshabilitadas en todos los modos.

## B. Estructura del proyecto

```
gpv-command-center/
├── backend/app/
│   ├── main.py              # create_app(): middlewares, errores, rutas, estáticos
│   ├── container.py         # inyección de dependencias y selección de fuente
│   ├── settings.py          # configuración desde entorno
│   ├── api/                 # auth_routes, data_routes, ops_routes, system_routes, deps
│   ├── core/                # db, security, errors, context (correlación), logging_config
│   ├── connectors/          # base (diagnóstico HTTP) y factorylogix (OData, xTend, FLX, archivos)
│   ├── data/                # models, source (interfaz), demo, external (CSV/OData)
│   └── services/            # audit, diagnostics, metrics, operations, labels
├── frontend/
│   ├── index.html
│   └── assets/{css/app.css, js/app.js, js/api.js, js/ui.js, js/charts.js, js/pages/*.js}
├── config/                  # *.example.json (copiar a *.json por instalación)
├── samples/aux_example/     # formato CSV de fuente auxiliar
├── scripts/                 # run_server.bat, run_tests.bat, build_offline_wheels.bat, *.sh
├── tests/                   # pytest: aislamiento DEMO, operaciones, diagnóstico, conectores, API
├── docs/                    # este documento, pantallas, integraciones, despliegue, seguridad, limitaciones
├── requirements.txt / requirements-dev.txt / .env.example
```
