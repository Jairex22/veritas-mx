# Arquitectura

## Visión general

```
Navegador (127.0.0.1)  ──fetch + X-CSRF-Token──▶  backend/server.py (ThreadingHTTPServer)
                                                     │
                                                 backend/api.py  (valida entradas)
                                                     │
          ┌──────────────── services/*_service.py (trazabilidad, pulse, quality, rework)
          │                        │                                   │
   analytics/ (reglas puras)   services/context.py ── fuente activa ──┤
                                   │                                   ├─ DemoDataSource (fixtures)
                         repositories/ ── SQLite                       └─ FactoryLogixODataClient ── HTTP ──▶ FactoryLogix
```

- **Sin dependencias externas.** `http.server`, `urllib`, `sqlite3`, `xml.etree`, `zipfile`, `ctypes`.
- **Fuente intercambiable.** `DemoDataSource` y `FactoryLogixODataClient` exponen `execute(QuerySpec) -> QueryResult` y `fetch_metadata()`. Los servicios no saben de dónde vienen los datos.
- **Consultas estructuradas.** El frontend envía parámetros; el backend construye un `QuerySpec` (entidad, filtros `campo/operador/valor`, orden, top). Nunca se acepta texto OData del usuario.

## Módulos

| Ruta | Responsabilidad |
|---|---|
| `models/results.py` | `ODataStatus` (17 estados explícitos) y `QueryResult` con tiempos, intentos, `stale`, `truncated` |
| `models/query.py` | `Filter`, `QuerySpec` |
| `models/entities.py` | Catálogo de propiedades verificadas, lista blanca de campos filtrables |
| `services/odata_filters.py` | Literales tipados (String/Guid/DateTimeOffset/Int/Boolean, v2–v4), escape de comillas, codificación URL, límites |
| `services/metadata.py` | Parseo EDMX, versión OData, comparación con el esquema esperado, rechazo de DOCTYPE |
| `services/odata_client.py` | HTTP, semáforo global, reintentos/backoff 429/5xx, sin redirecciones, sin proxy, límite de tamaño, paginación del mismo origen, política de seguridad, tiempos |
| `services/demo_source.py` | Fixtures + datos sintéticos + inyección de fallos |
| `services/traceability_service.py` | Módulo A con fallback a caché por fuente |
| `services/pulse_service.py`, `quality_service.py`, `rework_service.py` | Módulos B, C, D |
| `analytics/defects.py` | Agrupación por DefectID y clasificación ACTIVE/CLOSED/HISTORY_INCOMPLETE/UNKNOWN_STATUS |
| `analytics/timeline.py` | Fusión cronológica por instante UTC; fechas ausentes al final |
| `analytics/rework_rules.py` | Reglas R01–R09 con evidencia y "no se puede concluir" |
| `analytics/evidence.py` | Evidencia confirmada / inferencias / no verificable |
| `reports/` | Secciones neutrales → CSV (BOM, anti-fórmulas), XLSX (OOXML mínimo), HTML escapado |
| `repositories/` | Caché con `dedup_key`, auditoría, salud por entidad, historial, ajustes |
| `backend/server.py` | Host check, CSRF, CSP, límites, archivos estáticos sin traversal |

## Modelo de datos (SQLite)

`CachedSMTEvents`, `CachedQualityDefects`, `CachedQualityHistory`, `QueryAudit`, `SearchHistory`, `ConnectionHealth`, `AnalysisResults`, `ApplicationSettings`, `SchemaVersion`.

- `dedup_key = "key:<ODataKey>"` solo si `ODataKey` es un GUID válido **y no** `00000000-0000-0000-0000-000000000000`; en otro caso `hash:<sha256 del registro completo>`. Así, registros históricos distintos con el mismo DefectID no se sobrescriben y las ventanas superpuestas no duplican filas.
- `UNIQUE(data_source, dedup_key)`: demo y live nunca se mezclan.
- Índices por Identifier, Batch, fecha UTC y DefectID.
- Se guardan `raw_json` original y `first_seen_at`/`last_seen_at` (procedencia).

## Flujo de una consulta OData (modo real)

1. Política: modo `live` + `live_mode_approved` + (Basic solo con HTTPS o aprobación explícita).
2. `$metadata` (caché 60 min; si falla, tipos de respaldo y la consulta se marca "tipos no verificados").
3. Validación del filtro contra lista blanca **y** metadata.
4. Semáforo global (1 solicitud simultánea por defecto).
5. Solicitud con timeout; 429/500/502/503/504 → backoff y reintento (máx. 2); 401/403/timeout/red → sin reintento.
6. Validación estricta de la estructura JSON (`value` / `d.results`).
7. Auditoría en `QueryAudit`, `ConnectionHealth` y log diario.
8. Si falla: se sirve la última lectura válida de la caché marcada **desactualizada**, o se informa error explícito.

## Medición de tiempos

`wait_headers_ms` (red + procesamiento de FactoryLogix hasta cabeceras), `download_ms` (transferencia), `parse_ms` (aplicación), `backoff_ms`. Permite distinguir si el cuello de botella es red/servidor o la aplicación. Visible en Historial y Diagnóstico.
