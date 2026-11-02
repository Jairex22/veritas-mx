# Registro de cambios

## 1.0.0 — 2026-11-02

Primera versión completa.

* Núcleo: roles configurables (matriz rol × permiso), áreas, turnos, archivos privados con
  autorización, auditoría con ID de operación, notificaciones internas, cola de trabajos persistente
  (inline/worker, reclamo atómico, recuperación), diagnóstico, respaldo/restauración, datos demo opcionales.
* Comunicados con audiencia, prioridad, vigencia, adjuntos y confirmación de lectura; comentarios,
  dudas e incidencias genéricos; conversaciones.
* Producción: datasets (plan, incremental, snapshot, serial, calidad, genérico), asistente de
  importación XLSX/CSV con validación por fila/columna, modos, perfiles, errores exportables,
  importación por bloques con compensación, reversión sin destruir cambios posteriores; plan con
  historial de cambios, captura de avance, proyección declarada.
* Capa de métricas única: cumplimiento agrupado, pendiente, atraso, rechazo, scrap, FPY, OEE, Pareto.
* Dashboard con filtrado cruzado, detalle y exportación de la selección; constructor de dashboards
  con campos calculados seguros y unión validada.
* Reportes PDF/XLSX/CSV/DOCX/PPTX desde instantánea consistente; programación con planificador
  dedicado, deduplicación y recuperación.
* Hoja de cálculo virtualizada con motor de fórmulas propio (sin eval), versiones y control de conflictos.
* Centro de documentos: PDF, PPTX (nivel paquete OPC), XLSX/CSV, DOCX, conversión con LibreOffice opcional.
* Etiquetas: diseñador en mm, Code 128 propio verificado, QR, SVG/PDF a escala, ZPL, impresión por
  navegador o impresoras registradas con estados honestos, consecutivos transaccionales, reimpresión con motivo.
* Kaizen con flujo, 5 porqués, PDCA, antes/después, ahorros aprobados y A3.
* Correcciones durante la validación: candado global para PDFium (evita caída del servidor por
  miniaturas en paralelo), aislamiento REPEATABLE READ solo en transacción externa (PostgreSQL),
  restauración sin perfiles duplicados (PostgreSQL), dimensiones de elementos rotados en etiquetas,
  lectura robusta de `dataset` en formularios JS.
