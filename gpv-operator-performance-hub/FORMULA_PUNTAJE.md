# Explicación de la fórmula del puntaje operativo

Implementación de referencia: `backend/app/scoring.py`.

## 1. Fórmula

```
puntaje = calidad_norm       × peso_calidad        (35% por defecto)
        + ciclo_norm         × peso_ciclo           (25% por defecto)
        + productividad_norm × peso_productividad   (20% por defecto)
        + consistencia_norm  × peso_consistencia    (10% por defecto)
        + retrabajo_norm     × peso_retrabajo        (10% por defecto)
```

Los cinco pesos son editables desde **Configuración** (roles Administrador e
Ingeniero MES). Si no suman exactamente 100%, el sistema los **normaliza
automáticamente** antes de calcular (divide cada peso entre la suma total),
así que el resultado siempre es consistente.

## 2. Cómo se calcula cada componente

- **Calidad (FPY normalizado):** `100 × unidades_conformes / unidades_procesadas`,
  limitado a 0-100.
- **Cumplimiento de ciclo:** por cada evento, `100 × (tiempo_estándar /
  tiempo_real)`, limitado a 0-100; luego se **amortiguan los valores
  atípicos** (fuera de 3 desviaciones estándar del grupo, técnica de
  *winsorizing*) y se promedian. Esto evita que una sola orden pequeña o un
  cambio de producto distorsionen el resultado completo.
- **Productividad normalizada:** unidades procesadas por segundo activo real,
  comparado contra la tasa que implicaría el tiempo estándar del grupo de
  estaciones trabajadas, expresado como porcentaje (0-100).
- **Consistencia:** `100 × (1 − coeficiente de variación del tiempo de
  ciclo)`, limitado a 0-100. Un operador más estable entre unidades obtiene
  un valor más alto.
- **Retrabajo (invertido):** `100 − tasa_de_retrabajo`, con piso en 0. Menos
  retrabajo, más puntaje.

## 3. Reglas que se aplican siempre

1. **Los tiempos muertos autorizados se excluyen** antes de calcular ciclo y
   productividad (no penalizan al operador por una junta de turno o una
   actividad de 5S aprobada).
2. **Normalización por estación y producto:** cada componente se calcula
   usando el estándar de la estación específica de cada evento, de modo que
   operadores en estaciones o productos distintos no se comparan sin ajustar.
3. **Mínimo de muestras:** si el número total de unidades es menor al mínimo
   configurado (`min_units`, 20 por defecto), **no se publica un puntaje**.
   La clasificación es "Datos insuficientes" y se explica por qué
   ("Todavía no hay suficientes unidades para calcular una tendencia
   confiable.").
4. **Penalización suave de atípicos:** ver "amortiguación" arriba — nunca se
   descarta un evento, sólo se acerca su influencia hacia el rango normal del
   grupo.
5. **El resultado final se limita estrictamente a 0-100.**
6. **Se muestra el nivel de confianza de los datos** (Baja / Media-baja /
   Media / Media-alta / Alta), calculado a partir del número de unidades y de
   cuántos días distintos las componen. Nunca se oculta.
7. **El desglose (`breakdown`) siempre se expone**: cada componente, su valor
   crudo, su valor normalizado, su peso y su contribución al puntaje final,
   de modo que el resultado es siempre trazable — se puede explicar
   exactamente cómo se llegó a un número.

## 4. Clasificación

| Rango | Clasificación | Identidad visual |
|---|---|---|
| 90 – 100 | Excelente | Verde operacional |
| 80 – 89.99 | Bueno | Azul de referencia |
| 65 – 79.99 | En observación | Ámbar de atención |
| 0 – 64.99 | Requiere apoyo | Rojo de intervención (atenuado) |
| Muestra insuficiente | Datos insuficientes | Gris técnico |

## 5. Ejemplo numérico

Un operador con, en el periodo evaluado:

- Calidad normalizada: 98.1
- Cumplimiento de ciclo: 93.1
- Productividad normalizada: 100.0
- Consistencia: 40.7
- Retrabajo invertido: 98.6

Con los pesos por defecto:

```
puntaje = 98.1×0.35 + 93.1×0.25 + 100.0×0.20 + 40.7×0.10 + 98.6×0.10
        = 34.34 + 23.28 + 20.00 + 4.07 + 9.86
        = 91.5  →  "Excelente"
```

Este mismo cálculo, con cada término visible, es exactamente lo que la
aplicación muestra en la sección "Rendimiento actual" del detalle del
operador (campo `explanation` de la respuesta de la API).

## 6. Por qué estos valores y no una sentencia automática

El puntaje es una **entrada para una conversación**, no una conclusión. Por
eso la aplicación:

- Siempre acompaña el número con el desglose y el nivel de confianza.
- Incluye una sección de "Contexto del resultado" con factores que pueden
  explicarlo sin ser responsabilidad del operador (cambio de producto, orden
  pequeña, estación detenida, material faltante, equipo con falla, operador
  nuevo, baja cantidad de muestras, retrabajo, tiempo no productivo
  autorizado).
- Muestra, en toda la interfaz, el aviso: *"Este indicador es una
  herramienta de apoyo para mejora continua. Debe revisarse junto con el
  contexto operativo antes de tomar decisiones."*
