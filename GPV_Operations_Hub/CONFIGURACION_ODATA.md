# Configuración de FactoryLogix por OData (solo lectura)

FactoryLogix se integra **únicamente por OData y en modo lectura**. No se usan xTend API, xStream,
SQL directo, conexión a máquinas, carpetas vigiladas ni XML de máquinas. Ninguna captura del portal
escribe en FactoryLogix.

## Qué está confirmado y qué no

| Dato | Estado |
|---|---|
| Fuente permitida: OData de FactoryLogix, solo lectura | Confirmado |
| URL del servicio, versión OData, conjuntos de entidades, propiedades y claves | **POR CONFIRMAR** (se leen del `$metadata` real cuando GPV dé acceso) |
| Método de autenticación que el servidor admite realmente | **POR CONFIRMAR** |
| Campo de modificación fiable para incremental | **POR CONFIRMAR** (si no existe se usa ventana acotada) |
| Zona horaria de los instantes sin desfase | **POR CONFIRMAR** (supuesto documentado: America/Mexico_City) |

El paquete **no trae** ninguna URL, entidad ni campo real. Lo que aparece en el ejemplo es un
servicio **SIMULADO** (`tools/fake_odata_server.py`, entidad `EventosSimulados`) que existe solo para
probar el conector; no debe copiarse a la configuración real.

## Arquitectura

```
Navegador ──► Portal (127.0.0.1:8000) ──► servicio local del turno ──GET──► OData FactoryLogix
                     ▲                         (run_scheduler)
                     └── base de datos local (eventos con origen, clave externa, versión)
```

* El navegador **nunca** se conecta a OData ni recibe su dirección ni credenciales.
* Un solo servicio local sincroniza (`manage.py run_scheduler`, que INICIAR.bat abre minimizado;
  o `manage.py run_shift_service`). Un *lease* en la base de datos impide dos ciclos simultáneos.
* El cliente (`apps/shift/odata.py › ReadOnlyClient`) rechaza cualquier método distinto de GET.

## Credenciales (nunca en la base, el ZIP ni el chat)

En la conexión se guarda solo el **nombre** de la variable de entorno. En el equipo autorizado, con
la cuenta de Windows que ejecuta el portal (una vez; cierre y vuelva a abrir INICIAR.bat):

```bat
setx GPV_ODATA_USER "usuario-autorizado"
setx GPV_ODATA_PASSWORD "********"
```

| Tipo de autenticación | Qué usa | Nota |
|---|---|---|
| Sin autenticación | nada | Solo si GPV confirma que el servidor lo permite; no se supone |
| Básica | `GPV_ODATA_USER` + `GPV_ODATA_PASSWORD` | Exigir HTTPS si el servidor lo ofrece |
| Token (Bearer) | variable configurada en «secreto» | |
| Windows integrada (Negotiate) | cuenta del proceso | Requiere instalar `requests` y `requests-negotiate-sspi` (requirements-optional.txt). **No** se activa sola |

## Pasos para conectar (cuando GPV dé acceso)

1. Administración técnica › *Portal del turno › Conexiones OData* › Agregar: nombre, URL del servicio
   (la que entregue GPV), tipo de autenticación y nombres de variables. Línea del piloto.
2. *Mi turno › Fuentes › (conexión) › Diagnosticar por etapas*. Etapas y significado:

| Etapa | Falla típica | Qué significa |
|---|---|---|
| Conectividad e índice del servicio | `connectivity`, `timeout` | No hay red/VPN o la URL es incorrecta. **Un índice accesible NO demuestra acceso a datos** |
| Autenticación y lectura de `$metadata` | `auth` (401) | Credenciales/método no aceptados |
| Mapeo contra `$metadata` | `mapping` | Un campo mapeado no existe en el modelo real |
| Acceso real al conjunto de entidades | `forbidden` (403), `not_found` | Autenticado pero **sin permiso** a ese conjunto |

   La conexión solo queda **validada** si las cuatro etapas pasan, incluida una consulta real de
   máximo 5 registros (se muestra la muestra). Si no, no se puede activar.
3. En la misma página, elija el conjunto de entidades y mapee cada campo del portal a una propiedad
   del `$metadata` (lista desplegable). Defina la(s) clave(s) estable(s) y, si existe, el campo de
   modificación. Guardar el mapeo **invalida** la validación: vuelva a diagnosticar.
4. *Sincronizar ahora* para una prueba; luego *Activar sincronización automática* (60 s por omisión).

## Sincronización

| Regla | Implementación |
|---|---|
| Paginación | Sigue `@odata.nextLink` (v4) o `d.__next` (v2/v3) hasta `max_pages` (50) |
| `$select` | Solo propiedades mapeadas y claves |
| Filtro | `campo ge <instante>` con literal de la versión (v4 ISO, v2/v3 `datetime'…'`) |
| Incremental | Con campo de modificación: desde la última marca − solape (10 min) |
| Sin campo fiable | Ventana acotada (24 h) por el campo de tiempo del evento; se reconsulta completa |
| Claves | `(conexión, clave externa)` única para el registro vigente → upsert, nunca duplica |
| Correcciones de la fuente | Nueva versión del evento con historial (`EventRevision`) |
| Fallas | Reintentos con espera exponencial (máx. 1 h); la marca solo avanza si el ciclo completo termina bien |
| Datos ante falla | Se conserva el último dato con su hora; **nunca** se muestra cero por desconexión |
| Estado | Conectado · Con retraso (> 3 ciclos sin éxito) · Desconectado · Requiere revisión |
| Cada evento guarda | origen, clave externa, instante del evento, instante de recepción, modificación en la fuente, versión |

## Practicar sin GPV (simulado)

```bat
INICIAR_ODATA_SIMULADO.bat
```

Con datos de ejemplo cargados (`seed_demo`), la conexión «OData SIMULADO (no es FactoryLogix)» ya
apunta a `http://127.0.0.1:8765/odata/`. Todo lo que muestre está marcado como **SIMULADA / EJEMPLO**.
