# Archivos de ejemplo de formato

`aux_example/` muestra el **formato** esperado por la fuente auxiliar (`GPV_REAL_DATA_SOURCE=aux`).
Los seriales llevan el prefijo `EJEMPLO-`: no son datos de producción y sólo sirven para validar
la importación. Para uso real, apunte `GPV_AUX_DIR` a la carpeta donde se depositen las exportaciones
reales de FactoryLogix con las mismas columnas.

Columnas obligatorias de `events.csv`: `serial, timestamp (ISO-8601), station, result`.
Opcionales: `operation, work_order, assembly, revision, batch, line, area, operator, panel_id, details`.
