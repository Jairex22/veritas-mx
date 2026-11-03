# Fuentes de datos y mapeos

| Fuente | Qué aporta | Escritura | Estado en el piloto |
|---|---|---|---|
| FactoryLogix por OData | Eventos de producción por operación/estación, serie/panel, resultado, intento | **Solo lectura** (GET) | Conector listo; URL, entidades y campos **POR CONFIRMAR** con el `$metadata` real |
| Captura web del portal | Paros, ayudas/incidencias, faltantes de material, comentarios, listas de verificación, metas del turno, observaciones de calidad, captura manual de contingencia | En la base local del portal | Funcional |
| Archivos Excel/CSV (módulo «Cargar información») | Plan y producción por archivo | Base local | Herramienta opcional existente; no es la fuente del piloto |

No se usan xTend API, xStream, SQL directo, conexión a máquinas, carpetas vigiladas ni XML.

## Campos del portal ↔ propiedades OData

El mapeo se define en la página de la conexión, eligiendo propiedades que **existen** en el
`$metadata` real (el diagnóstico lo verifica). Ninguna propiedad se supone.

| Campo del portal | Uso | Obligatorio | Propiedad FactoryLogix |
|---|---|---|---|
| Clave(s) estable(s) | Evitar duplicados (upsert) | Sí | POR CONFIRMAR |
| Instante del evento | Ubicar en turno/periodo | Sí | POR CONFIRMAR |
| Instante de modificación | Incremental con solape | Recomendado | POR CONFIRMAR (si no es fiable → ventana acotada) |
| Orden | Meta y cumplimiento | Sí | POR CONFIRMAR |
| Operación / Estación | Operación de conteo, Top/Bottom | Sí | POR CONFIRMAR |
| Serie / Panel / Lote | Historial, conciliación, no duplicar | Recomendado | POR CONFIRMAR |
| Cantidad | Si falta y hay serie, vale 1 | Condicional | POR CONFIRMAR |
| Unidad | pz / panel | Opcional | POR CONFIRMAR |
| Resultado | PASS/FAIL (OK/NG se normalizan) | Recomendado | POR CONFIRMAR |
| Intento | Retest y FPY | Recomendado | POR CONFIRMAR |
| Lado | Top/Bottom | Opcional (la estación lo define) | POR CONFIRMAR |
| Alcance (snapshot) | Si la entidad es acumulada | Solo snapshot | POR CONFIRMAR |

## Estaciones y operaciones

Las estaciones del portal se dan de alta en *Administración técnica › Líneas* con el **código de
estación o de operación tal como llega de FactoryLogix**. Exactamente una debe marcarse
«cuenta como producto terminado del área» (operación de conteo). Los eventos cuya estación no
coincide no se cuentan y se informan.

## Simulación incluida (no es FactoryLogix)

`tools/fake_odata_server.py` publica `EventosSimulados` con propiedades `EventoId, Orden, Operacion,
Estacion, Parte, Serie, Panel, Lado, Cantidad, Resultado, Intento, Instante, Modificado`. Son
nombres **inventados para la simulación**; solo sirven para probar el conector y la interfaz.
