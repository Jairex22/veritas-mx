# Endpoints de la aplicación (GPV Operations HUB 2.0)

Todos requieren sesión iniciada; las acciones `POST` requieren token CSRF. Los permisos se validan en
el servidor (capacidades por rol, ver `CONFIGURACION_TURNOS_Y_ROLES.md`). Las respuestas JSON tienen
la forma `{"ok": true, "data": …}` o `{"ok": false, "error": "mensaje"}`.

## FactoryLogix (`/factorylogix/`, app `apps/flx`)

| Método | Ruta | Capacidad | Descripción |
|---|---|---|---|
| GET | `/factorylogix/` | `flx.status` | Connection Center (filtros `?categoria=` y `?estado=`) |
| POST | `/factorylogix/accion/` `action=test` (`schema=1` para leer `$metadata`) | `flx.admin` | Diagnóstico por etapas |
| POST | `/factorylogix/accion/` `action=probe`, `confirm=1`, `categoria` o `names[]` | `flx.admin` | Sondeo controlado `$top=1` (trabajo en segundo plano; responde `{"job_id"}`) |
| POST | `/factorylogix/accion/` `action=upload`, archivo `metadata` | `flx.admin` | Cargar `$metadata` guardado (sin verificar acceso) |
| POST | `/factorylogix/accion/` `action=retry_auth` / `reset_breaker` | `flx.admin` | Levantar el bloqueo tras 401 / la pausa por fallas |
| GET | `/factorylogix/reporte.json` | `flx.status` | Reporte de diagnóstico (estructura y estados, sin valores ni credenciales) |
| GET | `/factorylogix/api/estado/` | `flx.status` | Estado, última conexión exitosa, latencia, fecha del esquema, circuit breaker |
| GET | `/factorylogix/entidad/<EntitySet>/` | `flx.status` | Propiedades, claves, navegación, capacidades declaradas y verificadas |
| POST | `/factorylogix/entidad/<EntitySet>/accion/` `action=probe` o `caps` | `flx.admin` | Sondear una entidad / probar sus opciones OData |
| POST | `/factorylogix/entidad/<EntitySet>/consulta/` | `flx.query` | Consulta controlada (ver abajo). `format=csv` descarga CSV con línea de procedencia |

Parámetros de la consulta controlada: `select` (repetible), `f0_prop`/`f0_op`/`f0_value` … `f4_*`
(operadores `eq ne gt ge lt le startswith contains`), `orderby` + `dir` (`asc`/`desc`), `top`
(1…`GPV_FLX_MAX_TOP`), `count=1`. Respuesta:

```json
{"ok": true, "data": {"rows": [...], "count": 3, "pages": 1, "truncated": false, "latency_ms": 41,
  "source": {"entity_set": "WIP", "service_path": "/odata/WIP", "options": ["$top", "$filter"],
             "fetched_at": "2026-11-03T18:00:00+00:00", "schema_sha256": "1a2b3c4d5e6f", "origin": "FactoryLogix OData (lectura)"}}}
```

Errores: `400` validación (propiedad inexistente, opción no verificada, valor con tipo incorrecto);
`502` con `state` cuando FactoryLogix responde con error (`FORBIDDEN`, `TIMEOUT`, …); `403` sin permiso.

Línea de comandos: `manage.py flx_diagnose [--sondear --confirmar-sondeo] [--entidades A,B] [--retardo-ms N] [--salida carpeta]`.

## Portal del turno (`/turno/`) — existente

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/turno/api/estado/` | Hora del servidor, fuentes, órdenes y cumplimiento del contexto del usuario |
| GET | `/turno/api/pantalla/<línea>/` | Datos agregados de solo lectura para la pantalla del área |
| POST | `/turno/ayuda/` (JSON) | Crear solicitud de ayuda idempotente (`client_uuid`) |

Las demás rutas del portal del turno y de los módulos existentes son páginas HTML (ver `README_ES.md`).

## Otros endpoints JSON existentes

`/api/notificaciones/` (notificaciones), `/api/trabajos/<id>/` (progreso de trabajos),
`/analitica/api/dashboard/` (KPIs del dashboard de archivos importados), `/etiquetas/api/...` (diseñador e impresión).
