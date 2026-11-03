# Definiciones de datos e indicadores

Todas las vistas (tabla del plan, dashboard, API, Excel, PDF, DOCX, PPTX, CSV) usan
`apps/production/metrics.py`. Cada indicador devuelve `status`:
`ok`, `not_calculable` («No calculable») o `insufficient` («Datos insuficientes»), con su motivo.

## Fuentes y granularidad

* **Meta**: solo de `WorkOrder.qty_planned` (dataset tipo *Plan*). Una orden = un registro.
* **Buenas por orden**: suma de `qty_good` de registros **vigentes** de datasets marcados
  «cuenta como producción terminada» (incremental o snapshot):
  * Si el dataset define *estación de producción terminada*, solo cuentan registros de esa estación.
  * Si tiene varias estaciones y no la define, **se excluye** con advertencia (no se cuenta la misma pieza varias veces).
  * Snapshot (captura acumulada): solo cuenta la captura vigente de cada clave; nunca se suman capturas.
  * Si dos datasets reportan la misma orden, se usa el importado más recientemente y se advierte.
* Periodo del plan: órdenes cuyo **vencimiento** cae en el periodo (o inicio si no hay vencimiento);
  el avance de la orden es acumulado (todas las fechas). Las series por día/turno/hora usan la fecha del registro.

## Fórmulas

| Indicador | Fórmula | Reglas |
|---|---|---|
| Cumplimiento por orden | buenas / meta × 100 | Meta 0 o desconocida → «No calculable» |
| Cumplimiento agrupado | Σ buenas / Σ metas × 100 (órdenes con meta > 0) | Nunca promedio de porcentajes. Unidades distintas → «No calculable» (sin conversión sin factor documentado). Ej.: 80/100 y 150/200 → 230/300 = **76.67 %** (no 77.5 %) |
| Pendiente por orden | máx(meta − buenas, 0) | El excedente de una orden no compensa el faltante de otra. Ej. anterior: 20 + 50 = **70** |
| Atraso | vencimiento < ahora y pendiente > 0 | Vencimiento con solo fecha = 23:59:59 local (America/Mexico_City). Turnos en Administración › Turnos |
| Rechazo % | rechazo / (buenas + rechazo + scrap) × 100 | Supone disposiciones exclusivas del mismo periodo; si las fuentes no registran rechazo → «Datos insuficientes» |
| Scrap % | scrap / (buenas + rechazo + scrap) × 100 | Ídem. Retrabajo se reporta como cantidad, no se suma al total (las piezas retrabajadas terminan como buenas o scrap) |
| FPY | seriales que pasan en el **primer intento** / seriales con primer intento × 100 | Requiere dataset por serial con número de intento. Sin intento → «Datos insuficientes». Varias estaciones → filtrar una |
| OEE | Disponibilidad × Rendimiento × Calidad | Disponibilidad = (planeado − paro)/planeado; Rendimiento = ciclo ideal × conteo / tiempo operativo; Calidad = buenas/conteo. Sin minutos planeados, paro o ciclo ideal → «Datos insuficientes» |
| Pareto | Σ (rechazo + scrap) por causa, % acumulado | Si no hay cantidades, cuenta registros (se indica «registros») |
| Proyección de cierre | hoy + pendiente / (buenas de la ventana / días con producción) | Ventana 7 días, solo incremental; se muestra como **estimación** con fórmula y supuestos |

## Observaciones automáticas

Se generan solo con reglas sobre los datos (cumplimiento vs. referencia de 95 %, cantidad de atrasos,
línea con mayor pendiente, órdenes sin meta, antigüedad de datos > 24 h). **No** se infieren causas.

## Versión de datos

Cada reporte registra `data_version` (último lote, conteo de registros, último cambio del plan) y se
genera desde una instantánea tomada en una sola transacción (REPEATABLE READ en PostgreSQL;
transacción de escritura en SQLite). Todos los formatos del mismo reporte usan esa instantánea.

## Calidad de datos

La antigüedad mostrada es la de la última importación o captura; los datos **no** son en tiempo
real: cambian cuando alguien importa o captura. Las notificaciones se consultan cada `GPV_POLL_SECONDS`.


---

# Portal del turno (piloto SMT)

Implementación: `apps/shift/counting.py` y `apps/shift/services.py › shift_summary`. Las mismas
cifras alimentan Mi turno, la pantalla del área, el tablero, el relevo, el reporte en pantalla,
el PDF y el Excel (el reporte guarda una instantánea).

## Entidades

| Dato | Definición |
|---|---|
| Turno | Horario configurado en *Administración › Turnos*. Si fin ≤ inicio, cruza medianoche; su **fecha operativa** es la del inicio |
| Tiempo planeado | Duración del turno − descansos configurados |
| Meta del turno | Cantidad esperada en la operación de conteo para esa orden, línea, turno y fecha (*Metas*, con motivo e historial) |
| Operación de conteo | Estación marcada «cuenta como producto terminado del área»; solo sus eventos cuentan |
| Evento de producción | Registro con origen (OData, manual, sintético), clave externa, instante del evento, instante de recepción, versión y estado de conciliación |

## Indicadores del turno

| Indicador | Fórmula | Cuándo no se calcula |
|---|---|---|
| Buenas confirmadas | Σ eventos vigentes de la operación de conteo con resultado PASS (o sin resultado) de fuente automática + capturas manuales **aceptadas** | — |
| Manual pendiente | Σ capturas manuales pendientes o en revisión (se muestra aparte, no suma) | — |
| Pendiente | máx(meta − buenas confirmadas, 0) | Cantidades no comparables |
| Cumplimiento por orden | buenas confirmadas / meta × 100 | Sin meta («Datos insuficientes»); unidades no convertibles («No calculable») |
| Cumplimiento del turno | Σ buenas confirmadas / Σ metas × 100 | Unidades distintas o alguna orden no comparable |
| FPY | series que pasan en el primer intento / series con primer intento × 100 | Sin series con intento |
| Minutos de paro | Σ duración de paros que se traslapan con el turno (abiertos hasta ahora o hasta el fin) | — |

Reglas de conteo detalladas: ver `CONCILIACION_CAPTURA_ODATA.md` (Top/Bottom, retests, paneles,
snapshots, estaciones no mapeadas).

## Estados de reporte

Borrador → (Datos pendientes) → Revisado → Cerrado. Revisar exige resolver las excepciones
(paros sin motivo, paros abiertos, ayudas sin comentario). Cerrar con capturas pendientes o fuentes
sin actualizar exige un motivo (≥ 10 caracteres) que queda en el reporte. Datos que llegan después
del cierre crean una **revisión nueva** identificada; la cerrada se conserva.
