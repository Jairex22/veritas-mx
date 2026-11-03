# Validaciones pendientes contra FactoryLogix real

**Nada de lo siguiente se ha probado contra el servidor real.** El desarrollo no tuvo acceso a
`http://10.62.54.10:6065/odata/`. Todas las pruebas usaron un simulador y datos ficticios.
Ejecutar estas validaciones en una computadora autorizada de GPV, con la aplicación en `--live`,
y registrar el resultado.

| # | Validación | Cómo | Resultado esperado | Resultado GPV |
|---|---|---|---|---|
| 1 | Conectividad de red al puerto 6065 desde la PC | Estado de conexión → Verificar conexión | HTTP 200 de `$metadata` | ☐ |
| 2 | Mecanismo de autenticación aprobado por TI | Si 401: confirmar con TI; `auth_mode` | 200 sin almacenar credenciales | ☐ |
| 3 | `$metadata` se interpreta (EDMX V2/V3/V4) | Propiedades detectadas | Se identifica `ProductivityOverTime` y su EntityType | ☐ |
| 4 | Tamaño de `$metadata` < `MAX_METADATA_BYTES` (10 MB) | Verificar conexión | Sin error de tamaño | ☐ |
| 5 | Nombres reales de campos: fecha, cantidad, línea, estación, turno | Revisar con equipo MES y confirmar mapeo | Funciones sin campo = NO DISPONIBLE | ☐ |
| 6 | Significado del campo de cantidad (¿piezas buenas? ¿paneles? ¿acumulado?) | Equipo MES | Definir `analytics.quantity_unit_label` | ☐ |
| 7 | ¿Los registros son intervalos que se pueden sumar o valores acumulados? | Comparar con reporte FactoryLogix de un turno | Si son acumulados, **no** usar suma (ajuste requerido) | ☐ |
| 8 | `$top` respetado | Probar compatibilidad | "Límite de registros" = Comprobado | ☐ |
| 9 | Filtro por fecha y tipo EDM del campo | Probar compatibilidad | "Filtro por rango de fecha" = Comprobado | ☐ |
| 10 | Zona horaria de los timestamps (UTC vs local; `Edm.DateTime` sin zona) | Comparar un registro conocido con FactoryLogix | Horas coinciden en pantalla | ☐ |
| 11 | `$orderby` por fecha (y su costo en el servidor) | Probar compatibilidad + tiempo de respuesta | Comprobado y < 2 s | ☐ |
| 12 | `$select` | Probar compatibilidad | Comprobado | ☐ |
| 13 | Filtros por línea / estación / turno | Probar compatibilidad | Comprobado o se ocultan | ☐ |
| 14 | Formato JSON (Accept). Si responde Atom/XML | `append_format_json=true` | Respuesta JSON | ☐ |
| 15 | Paginación del servidor (`nextLink`) con `$top=50` | Consulta de 1 día | Se marca "resultado parcial" si aplica | ☐ |
| 16 | Volumen típico de registros por día/línea | Consulta de 1 día por línea | Ajustar `MAX_RECORDS` con TI/MES si 50 es insuficiente | ☐ |
| 17 | Tiempo de respuesta típico | Historial (ms) | < `REQUEST_TIMEOUT_SECONDS` | ☐ |
| 18 | Impacto en el servidor aceptable para TI/MES | Revisar historial y límites | Aprobación de límites | ☐ |
| 19 | Exportación Excel/PDF en equipos GPV | Exportar | Abre correctamente en Excel/Edge | ☐ |
| 20 | Prueba piloto con operadores | 1 turno | Flujo sin asistencia | ☐ |

## Supuestos que deben confirmarse

* El servidor acepta `Accept: application/json`.
* Para `Edm.DateTime` (sin zona) el servidor almacena hora local de planta.
* Turnos: el intervalo "Turno" agrupa por fecha calendario + valor del campo de turno; un turno
  nocturno que cruza medianoche aparecerá en dos grupos.
* La "línea con actividad" se determina por registros con cantidad > 0.

## Qué NO se debe hacer durante la validación

* No aumentar `MAX_RECORDS`, `MAX_CONCURRENT_REQUESTS` ni activar `AUTO_REFRESH_ENABLED` sin
  aprobación de TI/MES.
* No consultar otras entidades ni usar herramientas externas contra el servidor.
