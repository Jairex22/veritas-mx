# Arquitectura — GPV SMT Production Pulse v1.0.0

## Decisiones principales

| Decisión | Motivo |
|---|---|
| Solo biblioteca estándar de Python (`http.server`, `urllib`, `sqlite3`, `xml.etree`, `zipfile`) | Cero dependencias obligatorias: funciona descomprimiendo el ZIP en una cuenta estándar, sin pip, sin internet, sin bibliotecas obsoletas a futuro. Flask no aporta lo suficiente para este alcance (pocas rutas JSON). |
| XLSX generado con `zipfile` + SpreadsheetML | Excel nativo sin `openpyxl`. Validado abriendo en LibreOffice. |
| PDF mediante vista de impresión del navegador | Evita bibliotecas PDF pesadas; el navegador produce PDF fiel con gráficas SVG. |
| Autenticación Windows opcional (`requests-negotiate-sspi`) | `urllib` no implementa Negotiate/NTLM. Se carga solo si TI lo configura; usa la sesión actual, sin contraseñas. |
| DEMO como *transporte simulado* | El modo DEMO ejecuta el **mismo** cliente OData, caché, sondas y análisis que producción; solo cambia la capa de red. |
| Base SQLite separada para DEMO | Imposible mezclar datos simulados y reales (la base registra su modo y rechaza el otro). |

## Módulos

```
Navegador (HTML/CSS/JS nativo, SVG)
   │  JSON (solo 127.0.0.1, cookie de sesión HttpOnly, cabecera anti-CSRF)
   ▼
app.py ─────────── rutas HTTP, cabeceras de seguridad, validación de Host/Origin
   ▼
pulse_service.py ─ flujo de consulta, reglas de bloqueo, mapeo, diagnóstico, reportes
   ├── security.py ........ validación de entradas y literales OData
   ├── database.py ........ caché / historial / reportes / ajustes (SQLite WAL)
   ├── analytics.py ....... métricas solo con campos confirmados
   ├── report_generator.py  CSV, XLSX, snapshot para PDF
   ├── metadata_inspector.py  EDMX → esquema validado + sugerencias de campos
   ├── capability_probe.py  sondas $top=1 explícitas
   └── odata_client.py .... ÚNICO punto de salida de red
            ├── UrllibTransport / NegotiateTransport  (servidor real)
            └── DemoTransport (demo_source.py)       (simulador)
settings.py ─ config.json validado (rangos, tipos, entidad única, localhost)
timeutil.py ─ zona horaria de planta, parseo de fechas OData V2/V3/V4
```

Respecto a la estructura sugerida se añadieron `pulse_service.py` (separa reglas de negocio de
HTTP), `capability_probe.py` (las pruebas de compatibilidad son un concepto propio con evidencia
persistida), `demo_source.py`, `settings.py` y `timeutil.py`, y las pantallas JS se dividieron
por página (`production.js`, `dashboard.js`, `diagnostics.js`, `reports.js`) además de
`app.js` (núcleo) y `charts.js`.

## Tres niveles de evidencia

1. **Declarado**: la propiedad existe en `$metadata` (`metadata_inspector`).
2. **Anunciado**: anotaciones `Org.OData.Capabilities.V1.*` lo indican (solo informativo).
3. **Comprobado**: una sonda `$top=1` respondió 200 **y** el resultado es coherente (p. ej. los
   registros devueltos están dentro del rango; si no, el filtro se marca *falló* porque el
   servidor lo ignoró).

Las sondas se ligan al hash del esquema + mapeo; si cualquiera cambia, dejan de valer.

## Política de consultas (aplicada en código, con pruebas)

| Regla | Dónde |
|---|---|
| Solo `GET` a `$metadata` y `ProductivityOverTime` | `security.ensure_allowed_resource`, `ODataClient.build_relative_url` |
| `$top` obligatorio y ≤ `MAX_RECORDS` | `build_relative_url` |
| Una solicitud activa por proceso; la segunda se **rechaza** (no se encola) | `RequestGate` |
| Espaciado mínimo, presupuesto por sesión y global por hora | `RequestGate` |
| Circuit breaker (3 fallas → 300 s; `Retry-After` en 429) | `CircuitBreaker` |
| Sin reintentos, sin redirecciones, sin seguir `nextLink` | `ODataClient`, `_NoRedirect` |
| Respuesta máxima `MAX_RESPONSE_BYTES`, plazo total `REQUEST_TIMEOUT_SECONDS` | `_read_bounded` |
| Consulta bloqueada si `$top` o filtro de fecha no están comprobados | `PulseService.readiness` |
| Nunca sustituir una consulta filtrada fallida por una sin filtros | `run_query` devuelve el error |
| `$select`/`$orderby` solo si se comprobaron | `PulseService.build_spec` |
| Caché compartida entre usuarios locales (TTL 300 s) | `odata_cache` + firma normalizada |
| Sin polling; auto-refresco desactivado y rechazado por el backend | `AUTO_REFRESH_ENABLED=false` |
| Navegador no puede enviar consultas OData arbitrarias | La API acepta solo fechas/valores validados |

Consulta típica generada:

```
ProductivityOverTime?$select=<clave>,<fecha>,<cantidad>,<línea>...
  &$filter=<fecha> ge 2026-11-02T06:00:00Z and <fecha> lt 2026-11-04T06:00:00Z and <línea> eq 'SMT-L01'
  &$orderby=<fecha> desc&$top=50
```

## Base de datos (`data/production_pulse.db`)

* `odata_cache`: id de conjunto, firma, parámetros, URL relativa, fecha de consulta y expiración,
  registros (JSON), cantidad, `more_available` (truncado), estado de validación, hash de respuesta, hash de esquema. Máximo 3 instantáneas por firma.
* `query_history`: fecha, tipo (query/metadata/probe), consulta, ms, registros, HTTP, resultado,
  estado de caché (hit/miss/blocked), detalle técnico.
* `saved_reports`: id, generación, periodo, filtros, fuente, fecha de extracción, caché, snapshot.
* `application_settings`: mapeo confirmado, resultados de sondas, límites efectivos.

Retención: caché 7 días, historial 30 días, reportes 90 días, tamaño máximo 200 MB (se eliminan
las instantáneas más antiguas y se compacta). Sin credenciales en ninguna tabla.

## Seguridad

* Escucha en `127.0.0.1`; otro host requiere `allow_non_localhost` explícito.
* Validación de `Host` (anti DNS-rebinding), `Origin` y cabecera `X-Pulse-Request` en POST; cookie
  `HttpOnly; SameSite=Strict`; cuerpo JSON ≤ 16 KB.
* CSP estricta (`script-src 'self'`, sin scripts ni estilos en línea), `nosniff`, `DENY` frames.
* Frontend construye el DOM con `textContent` (todo dato se escapa).
* Valores de filtro con lista blanca de caracteres y comillas OData duplicadas; nombres de campo
  validados contra metadata; operadores en lista blanca.
* XML de metadata: rechazo de DTD/ENTITY, tamaño máximo.
* Logs rotativos con filtro que oculta Authorization/Cookie/contraseñas.
* Exportaciones protegidas contra inyección de fórmulas.

## Zona horaria

Las fechas del filtro se interpretan como días completos en hora local de la planta (reglas del
sistema operativo, o `analytics.plant_timezone`). Para `Edm.DateTimeOffset` se envía UTC; para
`Edm.DateTime` (sin zona) se envía hora local: **pendiente de validar en GPV**.

## Extensión futura

* Nuevos roles de campo: agregar a `settings.FIELD_ROLES`, `metadata_inspector._ROLE_HINTS`,
  `role_type_compatible` y una sonda en `capability_probe`.
* Nuevas métricas: `analytics.analyze` (siempre con estado verified/partial/unavailable).
* Otras áreas además de SMT: la entidad sigue siendo la única autorizada; se añadirían filtros.
