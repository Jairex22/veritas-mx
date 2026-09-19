# Diccionario de indicadores

Definición de cada indicador que muestra la aplicación, tal como aparece en
la interfaz (en español, sin jerga ambigua).

## Producción

| Indicador | Definición |
|---|---|
| **Operadores activos** | Operadores con al menos un evento de producción registrado en el periodo filtrado. |
| **Unidades procesadas** | Suma de unidades que pasaron por una estación (conformes + rechazadas), en el periodo. |
| **Unidades conformes** | Unidades que pasaron la estación sin defecto detectado, a la primera. |
| **Rechazos** | Unidades procesadas que resultaron con defecto y no fueron aceptadas. |
| **Retrabajos** | Unidades que requirieron un segundo paso por proceso (reproceso) para quedar conformes. |
| **Tiempo de ciclo (real)** | Tiempo real registrado para procesar una unidad en una estación. |
| **Tiempo de ciclo estándar** | Tiempo de referencia definido para esa estación (meta de proceso). |
| **Cumplimiento contra estándar** | `(tiempo estándar / tiempo real) × 100`. Mayor a 100% significa más rápido que el estándar. |
| **Cola estimada** | Aproximación del tiempo adicional por unidad respecto al estándar en una estación; no es una medición directa de WIP. |

## Calidad

| Indicador | Definición |
|---|---|
| **First Pass Yield (FPY)** | `(unidades conformes / unidades procesadas) × 100`. Unidades correctas a la primera, sin retrabajo. |
| **Tasa de defectos** | `(unidades rechazadas / unidades procesadas) × 100`. |
| **Tasa de retrabajo** | `(unidades reprocesadas / unidades procesadas) × 100`. |
| **Pareto de defectos** | Códigos de defecto ordenados de mayor a menor cantidad, con porcentaje acumulado, para priorizar causas raíz. |
| **Causa del defecto** | Clasificación del origen probable: Error de proceso, Material, Equipo, Programa, Diseño, Método, Posible error operativo o Causa sin confirmar. Nunca se asigna automáticamente al operador. |
| **Unidades bloqueadas** | Unidades retenidas por un hallazgo de calidad hasta su disposición. |
| **Validaciones fallidas** | Resultados de prueba/validación que no cumplieron el criterio de aceptación (p. ej. en ICT, FCT, Final Test). |

## Desempeño del operador

| Indicador | Definición |
|---|---|
| **Consistencia** | Estabilidad del tiempo de ciclo del operador: `100 × (1 − coeficiente de variación)`, limitado a 0-100. Un operador consistente varía poco entre unidades. |
| **Índice de consistencia** | Mismo cálculo que "Consistencia", mostrado en la tabla de Rendimiento. |
| **Nivel de confianza de los datos** | Qué tan confiable es el resultado según el número de unidades y de días distintos con actividad (Baja, Media-baja, Media, Media-alta, Alta). Ver `FORMULA_PUNTAJE.md`. |
| **Puntaje operativo** | Resultado 0-100 del motor de puntaje configurable. Ver `FORMULA_PUNTAJE.md`. |
| **Clasificación** | Excelente (90-100), Bueno (80-89.99), En observación (65-79.99), Requiere apoyo (0-64.99) o Datos insuficientes (por debajo del mínimo de unidades configurado). |
| **Tendencia** | Comparación del puntaje del periodo actual contra el periodo equivalente anterior: Mejorando, Estable o En descenso. |

## Capacitación

| Nivel | Significado |
|---|---|
| **No capacitado** | El operador no cuenta con capacitación registrada en esa estación. |
| **En entrenamiento** | Está aprendiendo el proceso, normalmente bajo supervisión directa. |
| **Supervisado** | Puede operar la estación con supervisión periódica. |
| **Certificado** | Cuenta con certificación vigente para operar la estación de forma independiente. |
| **Instructor** | Está certificado y autorizado para capacitar a otros operadores en esa estación. |

## Contexto del resultado (Detalle del operador)

Factores que la aplicación detecta automáticamente y que pueden explicar un
resultado sin ser responsabilidad del operador:

- **Cambio de producto** — el operador trabajó en un producto distinto al habitual en el periodo.
- **Orden pequeña** — el Work Order trabajado es de lote reducido (`is_small_batch`).
- **Estación detenida** — se registró un paro de la estación durante el turno del operador.
- **Material faltante** — tiempo muerto asociado a falta de material.
- **Equipo con falla** — tiempo muerto asociado a una falla de equipo.
- **Operador nuevo** — ingreso registrado hace menos de 30 días.
- **Baja cantidad de muestras** — el número de unidades en el periodo está por debajo del mínimo configurado para una clasificación confiable.
- **Trabajo de retrabajo** — el operador tuvo pases de retrabajo en el periodo.
- **Tiempo no productivo autorizado** — tiempo muerto aprobado (junta de turno, 5S, etc.), que se excluye del cálculo de ciclo y productividad.

## Alertas

| Categoría | Cuándo aparece |
|---|---|
| **Estación** | FPY por debajo de meta, tiempo real por encima del estándar, o sin actividad reciente. Se marca explícitamente como posible causa de proceso, no del operador. |
| **Operador** | Clasificación "Requiere apoyo", siempre acompañada de la nota de revisar el contexto de turno antes de asignar una acción de capacitación. |
| **Cobertura de datos** | Operadores con actividad pero por debajo del mínimo de unidades para clasificar. |
| **Certificación** | Certificaciones próximas a vencer (dentro de 30 días). |
