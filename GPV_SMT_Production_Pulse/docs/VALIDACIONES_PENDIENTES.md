# Validaciones pendientes y requisitos que dependen del esquema real

**No se ha probado nada contra el servidor real.** El entorno de desarrollo no tiene acceso a
`http://10.62.54.10:6065/odata/` (desde allí la conexión agota el tiempo de espera). Toda la
funcionalidad se verificó con un servidor OData simulado y datos ficticios. Los nombres de campos
del modo DEMO (`IntervalStart`, `GoodCount`, `LineName`, `WorkOrder`…) **son inventados para la
simulación** y no se asumen en el código: en modo real se usan los campos que declare `$metadata`.

## Bloqueo actual: HTTP 401 en ProductivityOverTime

Resultado observado en la PC de GPV (04/11/2026, v1.1.0):

* `GET $metadata` → **200** sin credenciales (se identificaron los campos).
* `GET ProductivityOverTime?$top=1` → **401** (el servidor exige autenticación para la entidad).

Desde la v1.1.1 la aplicación **no usa autenticación** por decisión de GPV. Mientras el servidor exija
credenciales para la entidad **no es posible recolectar datos**; la aplicación muestra el error, conserva
lo guardado y reintenta con espera creciente (10, 20, 40 min y después cada hora), sin consultas
repetitivas. Opciones para resolverlo, todas del lado de FactoryLogix/TI:

1. **Habilitar lectura anónima** de `ProductivityOverTime` en el servicio OData (como ya está `$metadata`),
   idealmente restringida a la IP de la PC de planta. No requiere cambios en la aplicación.
2. Si TI exige autenticación, se debe definir un mecanismo aprobado. Esta versión no lo implementa a
   propósito (no se guardan contraseñas); habría que acordarlo y desarrollarlo como cambio aparte.

En *Estado de conexión → Historial* y en el Monitor se muestra qué esquema pide el servidor
(por ejemplo `NTLM, Negotiate` o `Basic`); entrégaselo a TI junto con este documento.

## Requisitos que dependen de lo que exista en `ProductivityOverTime`

| Requisito | Qué se necesita del esquema | Si no existe | Cómo resolverlo |
|---|---|---|---|
| 1. Leer `$metadata` e identificar campos | EntitySet `ProductivityOverTime` en el EDMX | Metadata incompatible: no se consulta nada | Confirmar con el administrador de FactoryLogix el nombre exacto de la entidad |
| 2. Validar filtros de fecha y línea | Campo fecha/hora (`Edm.DateTimeOffset`/`DateTime`/`Date`) que acepte `$filter ge/lt`; campo de línea | Sin filtro de fecha: **recolección bloqueada** (nunca se consulta sin filtro). Sin filtro de línea: el recolector no lo necesita (lee todas las líneas y separa localmente) | Pedir a MES/TI que habiliten el filtrado por fecha en el servicio OData, o que expongan una entidad/vista ya filtrable (requiere nueva autorización) |
| 4. `$select`, `$top`, `$orderby` | Que el servidor los acepte | `$top` no comprobado → bloqueado. Sin `$select`: se reciben todos los campos (siempre limitados por `$top`). Sin `$orderby asc`: no se puede recuperar historial por partes; si una ventana excede `MAX_RECORDS` se registra como **hueco** | Habilitar `$orderby` o aumentar `MAX_RECORDS` con aprobación de TI |
| 6. Evitar duplicados | Clave (`Key`) del EntityType | Sin clave se usa hash de fecha + línea/estación/turno/proyecto/WO/producto; dos registros con esos mismos valores se tratarían como uno | Confirmar la clave real o qué campos identifican un registro |
| 7. Acumulado vs intervalo | Significado del campo de cantidad | Detección automática heurística; si es ambigua: **"indeterminada" y no se suman unidades** | MES confirma y se fija `collector.quantity_semantics` en `config.json` |
| 8. Líneas, proyectos, WO, productos | Campos de texto/entero con esos datos | La sección correspondiente **no se muestra** | Si están en otra entidad, se necesita autorización para consultarla (hoy está prohibido) |
| 10. Unidades e incrementos | Campo numérico de cantidad | Sin cantidad: recolección bloqueada (no hay métricas verificables) | Confirmar el campo con MES |
| 10. "Últimos 5 minutos" | Que FactoryLogix registre con ese detalle | Se muestra el **incremento entre las dos últimas lecturas** (≈5 min de hora de consulta) y su periodo real; la granularidad depende de cómo registre FactoryLogix | — |
| Hora del último registro | Campo de fecha con hora real de producción | Si el campo es solo fecha (`Edm.Date`), no hay hora | Confirmar con MES |

## Lista de verificación en una PC autorizada de GPV

| # | Validación | Cómo | Esperado | Resultado GPV |
|---|---|---|---|---|
| 1 | Conectividad al puerto 6065 | Monitor / Estado de conexión | `$metadata` HTTP 200 | ☑ (04/11/2026) |
| 2 | Lectura anónima de la entidad | Monitor sin error 401 | `ProductivityOverTime` responde 200 | ☐ (hoy: 401) |
| 3 | Campos reales | Estado de conexión → Propiedades | Se identifica fecha, cantidad, línea… | ☐ |
| 4 | Mapeo auto-detectado correcto | Comparar con MES y **Confirmar mapeo** | Origen "Confirmado" | ☐ |
| 5 | `$top` y filtro de fecha comprobados | Compatibilidad de consultas | Ambos "Comprobado" | ☐ |
| 6 | Filtro por línea comprobado | Compatibilidad de consultas | "Comprobado" (o justificar) | ☐ |
| 7 | Semántica de la cantidad | Comparar 1 turno con el reporte de FactoryLogix | Fijar `quantity_semantics` | ☐ |
| 8 | Zona horaria de los registros | Comparar un registro conocido | Horas coinciden | ☐ |
| 9 | Retraso de registro en FactoryLogix | Monitor → "diferencia con la última consulta" durante un turno | Documentar el retraso típico | ☐ |
| 10 | Volumen por ciclo ≤ `MAX_RECORDS` | Monitor → Últimas lecturas → "Recibidos" | Sin "Sincronizando" permanente | ☐ |
| 11 | Recuperación inicial | Primeros ciclos tras iniciar | Termina la sincronización | ☐ |
| 12 | Tiempo de respuesta | Últimas lecturas → ms | < 15 s | ☐ |
| 13 | Comportamiento ante caída | Desconectar red 15 min | Advertencia visible, reintentos espaciados, datos previos visibles | ☐ |
| 14 | Una sola instancia | Iniciar dos veces | La segunda termina con aviso | ☐ |
| 15 | Ejecución sin ventana | `pyw app.py --live` + acceso directo en `shell:startup` | Sigue recolectando sin navegador | ☐ |
| 16 | Carga aceptable para TI/MES | Revisar historial (1 consulta / 5 min) | Aprobación | ☐ |

## Supuestos explícitos

* Las fechas `Edm.DateTime` sin zona se interpretan en hora local de la planta.
* El campo de fecha identifica el **periodo de producción** de cada registro (no la hora de captura).
* Registros que FactoryLogix corrija tarde se capturan si caen dentro de `lookback_minutes` (15 min);
  correcciones más antiguas no se vuelven a leer (para no aumentar la carga).
* Contadores acumulados se agrupan por línea + estación; un valor menor que el anterior se trata
  como reinicio del contador.
