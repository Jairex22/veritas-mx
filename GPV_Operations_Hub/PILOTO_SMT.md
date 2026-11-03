# Piloto SMT · Portal del turno

## Alcance confirmado

* Área piloto: **SMT** de GPV Americas.
* Línea, operación de referencia (conteo) y turno específico: **POR CONFIRMAR**.
* Fuentes: captura web directa + FactoryLogix **solo por OData de lectura**.
* Primer arranque: la computadora Windows del usuario, en `127.0.0.1` (solo ese equipo).

## Lo que se entrega listo para el piloto

| Pantalla | Para quién | Qué hace |
|---|---|---|
| Mi turno | Todos | Contexto (sitio/área/línea/estación/turno/orden), siguiente acción, 4 acciones principales, avance de la orden, estado de fuentes |
| QR de estación | Operador | Identifica la **estación** (no a la persona); pide confirmar; nunca cambia el contexto en silencio |
| Mi trabajo / Buscar | Operador | Órdenes del turno con meta, buenas confirmadas, manual pendiente, pendiente, cumplimiento, FPY; historial por serie/panel/lote |
| Necesito ayuda | Operador → grupo | Motivos configurables, ruta a grupos, estados reportado → recibido → en atención → resuelto → verificado, relacionar duplicados, recordatorio y escalamiento **internos** |
| Paros | Operador | Inicio/fin, motivo (puede completarse al cierre), corrección con motivo e historial |
| Materiales | Operador → Materiales | Solicitud y estado; **no** es inventario |
| Instrucciones / listas | Operador | Revisión aprobada vigente por línea/operación/parte; listas de arranque/cambio con puntos no conformes que generan pendientes |
| Calidad | Operador / Calidad | Observación ≠ disposición; disposición solo por rol autorizado con referencia oficial |
| Imprimir etiqueta | Operador | Toma línea/estación/orden del contexto; Enter del escáner no imprime; sin trabajos ni consecutivos duplicados |
| Cierre / Reporte SMT del turno | Operador ve; supervisor revisa/cierra | Borrador automático al fin de turno, excepciones a resolver, revisado → cerrado, PDF/Excel, revisiones por datos tardíos |
| Relevo | Turno entrante | Resumen de pendientes; recibir **no** cierra incidencias |
| Supervisión, Metas, Conciliación | Supervisor | Tablero de líneas, metas por turno con motivo, decisión sobre capturas manuales |
| Pantalla del área | Pantalla en piso | Solo lectura, se actualiza sola, conserva el último dato si se pierde la conexión |
| Fuentes | Administrador | Diagnóstico por etapas, mapeo, sincronización, lagunas |

## Preparación del piloto (lista para GPV)

1. Confirmar línea, estaciones y **código de la operación de conteo** tal como aparece en FactoryLogix.
2. Confirmar turno(s), horarios y descansos (cruce de medianoche soportado).
3. Confirmar grupos de atención (Mantenimiento, Calidad, Materiales, Ingeniería, Pruebas, Supervisión) y sus integrantes.
4. Confirmar motivos de ayuda y de paro, minutos de recordatorio y escalamiento.
5. Entregar URL OData, método de autenticación y una cuenta de lectura; ejecutar el diagnóstico.
6. Revisar con Calidad la lista de disposiciones y la referencia del registro oficial.
7. Imprimir los QR de estación (`/turno/estacion/<código>/`, ver *Administración técnica › Líneas*).
8. Asignar a cada operador su área SMT; a cada responsable su grupo.

## Datos de ejemplo

`seed_demo` (o `seed_smt_pilot`) crea la línea **SMT-EJEMPLO** con estaciones `SMT-EJ-*`, motivos,
grupos, una lista de arranque, una instrucción y una conexión **OData SIMULADA**. Todo está marcado
«EJEMPLO/SIMULADA/sintético» y no describe la planta real.

## Medición del piloto (a realizar con personal real)

No se presentan resultados con usuarios reales: **no participó personal de GPV** en estas pruebas.
Se propone medir durante 2 semanas: tiempo de respuesta a ayudas (reportado → recibido → resuelto),
paros sin motivo al cierre, capturas manuales y su resultado de conciliación, reportes cerrados a
tiempo, uso de «Mi turno» por estación y comentarios de operadores/supervisores. Los datos salen de
las tablas del portal (auditoría y eventos), sin herramientas externas.

## Guion de la primera prueba con operadores y supervisores

Duración sugerida: 1 turno. Participan 2–3 operadores, 1 supervisor, 1 integrante de Mantenimiento
o Calidad y un observador que anota. Antes de empezar, cronometre el método actual («antes»).

| # | Tarea | Quién | Qué medir |
|---|---|---|---|
| 1 | Entrar, escanear el QR de la estación y confirmar la orden | Operador | Tiempo hasta ver «Meta del turno»; ¿necesitó ayuda? |
| 2 | Consultar el plan del turno y lo pendiente de su orden | Operador | Tiempo; ¿entendió «buenas confirmadas» vs «manual pendiente»? |
| 3 | «Necesito ayuda» → Falla de equipo, con comentario | Operador | Tiempo de registro; tiempo hasta «Recibido» y «Resuelto» |
| 4 | Recibir, atender, resolver; el operador verifica | Mantenimiento / Operador | Tiempos por estado; errores de permiso |
| 5 | Iniciar y terminar un paro con motivo | Operador | ¿Quedó algún paro sin motivo al cierre? |
| 6 | Imprimir una etiqueta desde el contexto (y escanear con Enter) | Operador | Tiempo; ¿alguna impresión accidental? Validar la etiqueta física con `GUIA_VALIDACION_ETIQUETAS.md` |
| 7 | Revisar cierre: completar excepciones | Operador | Número de excepciones; tiempo |
| 8 | Revisar y cerrar el reporte; abrir el PDF | Supervisor | Tiempo; diferencias contra el reporte actual |
| 9 | Recibir el relevo | Turno entrante | ¿Faltó algún pendiente? |

Registre por tarea: tiempo, errores, veces que pidió ayuda y comentarios textuales. Compare con
«antes». **Estos resultados no existen todavía**: deben levantarse con personal real de GPV.
