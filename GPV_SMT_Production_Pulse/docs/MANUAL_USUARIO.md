# Manual de usuario — GPV SMT Production Pulse

## Uso básico (operadores)

1. Abrir **http://127.0.0.1:8765**.
2. Elegir **Fecha inicial** y **Fecha final** (por defecto: hoy).
3. Elegir **Línea SMT** si el filtro aparece (escribir o seleccionar de la lista).
4. Presionar **Consultar producción**.
5. Revisar tarjetas, gráficas y tabla.
6. Exportar con **Exportar Excel**, **Exportar PDF** o **Exportar CSV**.

Un filtro (línea, estación, turno) **solo aparece si existe en FactoryLogix y se comprobó que
funciona**. Si no lo ves, no está disponible todavía.

## Botones

| Botón | Qué hace |
|---|---|
| Consultar producción | Consulta el periodo. Si otra persona consultó lo mismo hace menos de 5 min, se reutiliza la caché (no se molesta al servidor). Se deshabilita mientras consulta. |
| Ver última consulta | Muestra la última información guardada en este equipo, **sin** consultar FactoryLogix. |
| Exportar Excel | Descarga un `.xlsx` con hojas Resumen, Datos y Series. |
| Exportar PDF | Abre la vista de reporte y el cuadro de impresión: elegir **Guardar como PDF**. |
| Exportar CSV | Descarga un CSV UTF-8. |
| Limpiar filtros | Regresa a la fecha de hoy y quita filtros. |
| Ignorar caché… (casilla) | Fuerza actualizar desde FactoryLogix; solo se permite si la última extracción tiene más de 60 s. |

## Estados

| Estado | Significado |
|---|---|
| CONSULTANDO | Hay una solicitud en curso. |
| DATOS DISPONIBLES | Datos recién obtenidos de FactoryLogix. |
| INFORMACIÓN DESDE CACHÉ | Datos vigentes (menos de 5 min) guardados localmente. |
| INFORMACIÓN GUARDADA | Datos antiguos: **no representan la producción actual**. Se indica cuándo se extrajeron. |
| SIN REGISTROS | FactoryLogix no tiene registros para ese periodo y filtros. |
| SERVIDOR NO DISPONIBLE | No se pudo consultar. Se ofrece ver la última información guardada. |
| DATOS NO VERIFICABLES | La consulta se bloqueó o la respuesta no es confiable (ver motivo). |

La fecha **Extraído:** en la barra de estado indica cuándo se obtuvo realmente cada dato.

## Tarjetas

* **Producción registrada**: suma del campo de cantidad confirmado (la unidad indica el campo).
* **Productividad por periodo**: promedio por hora/día/turno **con registros**.
* **Tendencia vs periodo anterior**: compara con el periodo anterior de igual duración. Si no
  está guardado, el botón **Consultar periodo anterior** hace una única consulta adicional.
* **Líneas con actividad registrada**.
* **Última actualización confirmada**.

Cada tarjeta indica **VERIFICADO**, **PARCIAL** (p. ej. se alcanzó el límite de 50 registros) o
**NO DISPONIBLE**. La aplicación **no calcula** OEE, eficiencia, FPY, disponibilidad ni unidades
por hora, porque la entidad no provee definiciones confirmadas.

**Posibles disminuciones** es un indicador heurístico: intervalos completos al menos 25 % por
debajo de la mediana del periodo. Sirve para revisar, no es un diagnóstico.

Si aparece "resultado parcial", reduce el periodo o aplica un filtro de línea.

## Tendencias

Compara dos consultas guardadas (Periodo A vs Periodo B) por total y por línea. **No consulta
FactoryLogix**: usa solo información guardada dentro de la política de retención (7 días).

## Reportes

Lista de reportes generados (90 días de retención), con PDF, Excel, CSV y Eliminar. Cada reporte
incluye: aplicación, fecha de generación, periodo, filtros, métricas verificadas, tabla, gráficas
(PDF), fecha de extracción OData, si provino de caché y limitaciones.

## Estado de conexión (administrador / ingeniería)

* **Verificar conexión**: descarga y valida `$metadata` (sin descargar registros).
* **Mapeo de campos**: asigna los campos reales a cada función.
* **Probar compatibilidad**: pruebas de lectura con `$top=1`.
* Estado del circuit breaker, último HTTP, tiempos, caché e historial de solicitudes.

Diferencia clave: *conectividad* (el servidor respondió) **no es** *validez funcional* (que los
filtros funcionen). La pantalla lo indica explícitamente.

## Modo DEMO

La franja amarilla **MODO DEMOSTRACIÓN** indica datos **simulados**. Nunca se mezclan con datos
reales (base de datos separada). Los reportes DEMO llevan la marca y el prefijo `DEMO_`.
