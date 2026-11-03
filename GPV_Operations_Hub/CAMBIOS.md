# Cambios

## 1.1.0 · 2026-11-03 · Portal del turno (piloto SMT)

Agregado (sin modificar tablas existentes; migración `shift/0001_initial`):

* **Mi turno**: contexto sitio/área/línea/estación/turno/orden, QR que identifica la estación (con
  confirmación), cambio de orden con motivo y registro, siguiente acción, 4 acciones principales,
  vistas por rol y grupos combinados, actualización periódica con aviso de datos antiguos.
* **Conector OData de FactoryLogix solo lectura** (backend): diagnóstico por etapas (conectividad,
  autenticación/`$metadata`, mapeo, acceso real al conjunto), autenticación básica/token/Windows
  opcional con secretos solo en variables de entorno, paginación por enlaces de continuación,
  `$select`, filtros, upsert por clave estable, correcciones como versiones, incremental con solape
  o ventana acotada, reintentos con espera, estado de la fuente, lagunas registradas.
* **Servicio local único** (`run_scheduler`/`run_shift_service`) con *lease*: sincroniza, recuerda y
  escala internamente y genera borradores de reporte al terminar el turno sin pestañas abiertas.
* **Captura web**: paros (inicio/fin/corrección con historial), ayudas con enrutamiento a grupos,
  estados y verificación, materiales (sin inventario), observaciones de calidad vs disposiciones,
  instrucciones con revisiones y listas de verificación, metas del turno con motivo, captura manual de
  producción «pendiente de conciliación».
* **Conciliación** captura manual ↔ OData (mismo hecho no suma dos veces; lotes independientes sí;
  casos ambiguos a revisión) y reglas de conteo (operación de conteo, Top/Bottom, retests, FPY por
  primer intento, paneles con factor confirmado, snapshots).
* **Reporte SMT del turno** (borrador/datos pendientes/revisado/cerrado, PDF y Excel, cruce de
  medianoche, descansos, revisiones por datos tardíos, una vez por periodo) y **relevo digital**.
* Etiquetas desde el contexto del turno; el «Enter» del escáner ya no puede imprimir.
* Tablero de supervisión, pantalla del área de solo lectura, búsqueda por serie/panel/lote,
  propuesta Kaizen desde ayudas repetidas, cola sin red de solicitudes de ayuda (idempotente).
* Servicio OData **SIMULADO** para pruebas (`tools/fake_odata_server.py`) y configuración de EJEMPLO
  (`seed_smt_pilot`). `INICIAR.bat` abre el servicio local minimizado y solo escucha en 127.0.0.1.

Corregido:

* Formularios con varios botones (`name`/`value`): la protección contra doble envío deshabilitaba el
  botón y el navegador omitía su valor. Efecto real: en un trabajo de etiqueta, «Confirmar impresión
  física» se registraba como **fallido**. Ahora se conserva el valor del botón pulsado (prueba E2E).
* Vista previa de etiqueta desbordaba en celulares (ancho fijo de 420 px).
* Detalle de una orden mostraba registros de producción de otra área (y el enlace a su lote) a
  usuarios sin acceso a esa área.

## 1.0.1 — 2026-11-02

Corrección tras una auditoría por roles (operador, supervisor, analista) en navegador real.
Sin cambios de esquema de base de datos: `migrate` no requiere migraciones nuevas y los datos se conservan.

Fallos corregidos:

* **F1** El menú mostraba «Cargar información» y «Hoja de cálculo» a roles sin permiso (403 al abrirlos).
  Ahora cada sección del menú y los accesos de Inicio se muestran según los permisos del rol.
* **F2** Los enlaces «Lote #N» de la trazabilidad de una orden daban 403 a quien no había creado el lote.
  El detalle del lote es visible (solo lectura) para quien puede ver producción del área; el archivo
  original y el de errores solo para quien importa o revierte en esa área.
* **F3** Una incidencia o duda registrada en una orden no notificaba a nadie con permiso para resolverla.
  Ahora se notifica a los responsables del área y existe la bandeja «Incidencias y dudas» (filtros por
  tipo y estado) y un resumen en Inicio.
* **F5** (seguridad) Un supervisor de otra área podía ver y **revertir** importaciones ajenas: la reversión
  y el historial de importaciones ahora respetan el área.
* **F6** (seguridad) Trabajos de etiquetas (ver/reimprimir) y configuración de datasets ahora respetan el área.
* **F7** Lotes cuyo archivo trae su propia columna «Área» eran inaccesibles para usuarios de esas áreas.
* **F8** (pérdida de datos) En la hoja de cálculo, si el recálculo del servidor llegaba mientras el
  usuario escribía, lo tecleado se perdía (p. ej. `=SUMA(A1;6)` quedaba como `6)`).
* **F9** (grave, presente en 1.0.0) La página de detalle de **todo** reporte («Abrir resultado») daba
  error 500 por una variable de plantilla con guion bajo. Se agrega una prueba que compila todas las plantillas.
* **F4** Instalación en Windows: el instructivo usaba `C:\Users\<usuario>\…` y no advertía que «Extraer
  todo» crea dos carpetas con el mismo nombre. Se agregan `INSTALAR.bat` e `INICIAR.bat` (doble clic) y un
  comando de PowerShell que localiza la carpeta correcta; sección para actualizar conservando datos.

Pruebas nuevas: `apps/core/tests/test_role_flows.py` (regresiones F1–F9, compilación de todas las plantillas), `tools/e2e_roles.js`
(19 flujos por rol), `tools/e2e_crawl_roles.js` (recorrido de enlaces por rol) y escritura a velocidad
humana en `tools/e2e_smoke.js` (F8).

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
