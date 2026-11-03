# FactoryLogix Connection Center · conector OData (solo lectura)

Servicio autorizado por GPV: `http://10.62.54.10:6065/odata/` (metadatos en `…/odata/$metadata`).
Es una dirección de la **red interna** de GPV: solo responde desde un equipo conectado a esa red.
Este paquete se construyó y probó **sin acceso** a ese servidor, contra un servicio OData simulado.

## 1. Ejecutar el diagnóstico en la red de GPV (Windows 11)

En la carpeta que contiene `manage.py` (ya instalada con `INSTALAR.bat`):

* **Sin terminal:** doble clic en `DIAGNOSTICO_FACTORYLOGIX.bat`.
* **Con terminal**, un comando a la vez:

```bat
.venv\Scripts\python.exe manage.py flx_diagnose
```

Etapas que se muestran (cada una con estado y tiempo):

| Etapa | Qué verifica | Estados posibles |
|---|---|---|
| Configuración | URL válida y modo de autenticación | CONFIG ERROR |
| Métodos de autenticación | GET anónimo: si el servidor pide autenticación, qué métodos ofrece (`WWW-Authenticate`) | UNREACHABLE, TIMEOUT… |
| Documento de servicio | Índice del servicio (HTTP 200 **no** prueba acceso a datos) | AUTHENTICATION REQUIRED, FORBIDDEN, SERVER ERROR… |
| Lectura de `$metadata` | XML completo: EntitySets, tipos, claves, navegación, FunctionImports, anotaciones | BAD RESPONSE, AUTHENTICATION REQUIRED… |

Al terminar se guardan en `data\diagnosticos\` un `.json` y un `.md` con **estructura y estados**
(sin valores de registros, sin credenciales, sin encabezados). Revíselos antes de compartirlos.

### Sondeo controlado (solo con autorización del administrador MES)

```bat
.venv\Scripts\python.exe manage.py flx_diagnose --sondear --confirmar-sondeo
```

Hace **una** consulta `GET <EntitySet>?$top=1` por conjunto, en serie, con pausa
(`GPV_FLX_PROBE_DELAY_MS`, 500 ms por omisión). Se detiene si recibe 401, si el servidor deja de
responder o si se abre el *circuit breaker*. Para limitarlo: `--entidades WIP,Quality,Faults`.
De cada respuesta se guardan solo los **nombres** de propiedades devueltos, nunca sus valores.

## 2. Autenticación

El conector **no supone** ningún método. Con `GPV_FLX_AUTH=auto` (valor inicial) solo detecta lo
que el servidor ofrece. Según el resultado, configure en `.env`:

| El servidor ofrece | `GPV_FLX_AUTH` | Requisitos en el equipo |
|---|---|---|
| Responde sin credenciales | `none` | — |
| `Basic` | `basic` | Variables de entorno `GPV_FLX_USER` y `GPV_FLX_PASSWORD` (cuenta de servicio de solo lectura). Exija HTTPS si el servidor lo ofrece |
| `Negotiate` (Kerberos/NTLM) | `negotiate` | `pip install requests==2.32.3 requests-negotiate-sspi==0.5.2`; usa la sesión de Windows de quien ejecuta el portal |
| `NTLM` con usuario de servicio | `ntlm` | `pip install requests==2.32.3 requests-ntlm==1.3.0 pyspnego==0.11.2` y `GPV_FLX_USER=DOMINIO\usuario`, `GPV_FLX_PASSWORD` |

Credenciales: **solo** como variables de entorno del usuario de Windows, por ejemplo:

```bat
setx GPV_FLX_USER "DOMINIO\usuario_servicio"
```

(cierre y vuelva a abrir la ventana después de `setx`). Nunca se guardan en la base de datos, en
`.env.example`, en JavaScript ni en reportes; los encabezados de autorización nunca se registran.

Tras un **401** el conector deja de llamar al servidor (no reintenta credenciales rechazadas). Se
reanuda cuando cambia la configuración de autenticación o cuando un administrador pulsa
«Reintentar autenticación» en el Connection Center.

## 3. Connection Center (`/factorylogix/`)

| Rol | Ve | Puede |
|---|---|---|
| Administrador | Todo | Probar conexión, leer `$metadata`, sondeo controlado (con casilla de autorización), probar capacidades por entidad, cargar un `$metadata` guardado, reintentar autenticación, reanudar tras pausa, consultas controladas |
| Supervisor, Ingeniero | Estado, catálogo, propiedades | Consultas controladas a entidades verificadas, exportar CSV |
| Técnico | Estado, catálogo, propiedades | — |
| Operador | — (sin acceso) | — |

Muestra: estado del servicio, última conexión exitosa, latencia, modo de autenticación y métodos
ofrecidos, esquema (origen, fecha, versión, conteos), entidades verificadas / no disponibles /
sin permiso, entidades de la lista de GPV que **no** aparecen en el `$metadata`, FunctionImports con
sus parámetros (no se invocan) e historial de pruebas.

Estados: `CONNECTED`, `AUTHENTICATION REQUIRED`, `FORBIDDEN`, `ENDPOINT NOT FOUND`, `TIMEOUT`,
`SERVER ERROR`, `NO DATA`, `SCHEMA MISMATCH`, y además `UNREACHABLE` (sin red), `RATE LIMITED`
(429), `BAD RESPONSE` (200 que no es OData, p. ej. página de proxy), `BAD REQUEST` (400),
`CIRCUIT OPEN`, `CONFIG ERROR`, `NOT TESTED`. Nunca se muestra «conectado» sin una respuesta válida.

## 4. Consultas controladas (motor `apps/flx/query.py`)

* Solo EntitySets presentes en el `$metadata` real **y** confirmados por el sondeo.
* Solo propiedades/navegación declaradas; operadores fijos (`eq ne gt ge lt le startswith contains`);
  valores convertidos a literales según el tipo Edm y la versión OData (texto escapado: no hay inyección).
* Cada opción (`$select $filter $orderby $skip $count $expand`) se usa solo si «Probar capacidades»
  confirmó que el servidor la acepta para esa entidad. `$top` queda confirmado por el sondeo.
* Paginación real siguiendo `@odata.nextLink` / `__next`, que debe apuntar al mismo servidor y ruta
  (si no, se rechaza). Límites: `GPV_FLX_MAX_TOP`, `GPV_FLX_MAX_PAGES`, `GPV_FLX_MAX_ROWS`; el
  resultado indica si quedó truncado.
* Cada resultado indica entidad, opciones usadas, fecha de consulta y huella del esquema.

## 5. Robustez

| Mecanismo | Configuración |
|---|---|
| Tiempo límite por solicitud | `GPV_FLX_TIMEOUT` (20 s) |
| Reintentos solo en transitorios (timeout, 429 con `Retry-After`, 502/503/504) | 2, con pausa creciente |
| Sin reintento | 400, 401, 403, 404 |
| Circuit breaker | `GPV_FLX_BREAKER_FAILURES` (5) fallas → pausa `GPV_FLX_BREAKER_COOLDOWN` (120 s) |
| Concurrencia | `GPV_FLX_CONCURRENCY` (3) solicitudes simultáneas por proceso |
| Caché corta de respuestas correctas | `GPV_FLX_CACHE_SECONDS` (30 s) |
| Cancelación | El navegador puede cancelar la consulta en curso (botón «Cancelar») |
| Proxy | Desactivado para el servidor interno (`GPV_FLX_USE_SYSTEM_PROXY=false`) |
| Registros | `data\logs\gpvhub.log`, líneas JSON con ruta, nombres de opciones, estado y ms (sin valores de filtro ni encabezados) |

## 6. Si no hay red de GPV

El portal y sus módulos siguen funcionando; el Connection Center mostrará `UNREACHABLE` o `TIMEOUT`.
Para revisar la estructura sin red: un administrador puede cargar un `$metadata` guardado (XML); se
marca «Cargado de archivo (sin verificar acceso)» y no permite sondear ni consultar.
