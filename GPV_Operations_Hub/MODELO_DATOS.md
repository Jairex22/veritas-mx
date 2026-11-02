# Modelo de datos

Fechas y horas se almacenan en **UTC** (`USE_TZ=True`) y se muestran/programan en
**America/Mexico_City**. Fechas sin hora (columna «Fecha») se guardan como fecha local.
Identificadores de órdenes, partes, seriales y lotes son **texto** (conservan ceros iniciales).

## Núcleo (`apps/core`)

| Modelo | Propósito | Campos clave |
|---|---|---|
| Area | Áreas de planta | code (único), name, active |
| Shift | Turnos / calendario | code, start, end |
| Profile | Rol y alcance del usuario | user, role (admin/supervisor/engineer/operator), areas (M2M), all_areas, shift, must_change_password |
| RoleCapability | Matriz configurable rol × permiso | role, capability, allowed (único por par) |
| StoredFile | Archivo privado (fuera de /static) | id UUID, relpath, original_name, size, sha256, owner, area, visibility (private/area/all), parent (derivado de), source |
| AuditLog | Auditoría de cambios importantes | ts, actor, action, object_type/id, area, summary, changes JSON, op_id |
| Notification | Notificación interna | user, title, body, url, level, read_at |
| Job | Trabajo persistente | id UUID, kind, params, status, progress, result, error, attempts, heartbeat, locked_by, cancel_requested, idempotency_key (único) |
| SchedulerLease | Candado del planificador | name, holder, expires_at |

## Producción (`apps/production`)

| Modelo | Granularidad | Notas |
|---|---|---|
| Dataset | Fuente lógica | kind: plan / incremental / snapshot / serial / quality / generic; key_fields (claves de registro); finished_station; counts_as_production; version |
| MappingProfile | Perfil reutilizable | dataset + name único; mapping {campo: encabezado}; opciones (fecha, decimal, separador) |
| ImportBatch | Un archivo importado | archivo original conservado (StoredFile), sha256, hoja, modo (append/upsert/replace), alcance, mapping, status, stats conciliadas, archivo de errores, versión resultante del dataset |
| WorkOrder | **1 por número de orden** | number único (texto), meta, prioridad, vencimiento, estado, responsable, assigned_users, version |
| PlanChange | Historial del plan | campo, anterior, nuevo, motivo, usuario, lote (si viene de importación) |
| ProductionRecord | **1 por clave vigente por dataset** | record_key (de key_fields), is_current; restricción única (dataset, record_key) **cuando is_current**; cantidades Decimal; serial/estación/intento/causa; extra JSON para columnas no estándar |
| RecordChange | Imagen previa para revertir | batch, record, action (create/update/supersede/remove), before JSON |

Reglas: un *snapshot* nuevo marca el anterior `is_current=False` (historial) y crea uno nuevo;
la reversión restaura solo lo que no cambió después (conflictos reportados).
Las uniones de datos se hacen por orden (N registros → 1 orden); el constructor de dashboards valida
la cardinalidad antes de unir para no multiplicar cantidades.

## Comunicación (`apps/comms`)

Announcement (audiencia por áreas/turnos/grupos/roles, prioridad, vigencia, adjuntos, versión),
AnnouncementRead (leído/confirmado por usuario), Comment (genérico: orden, comunicado, Kaizen…;
tipo comentario/duda/incidencia, resuelto), Conversation/Message/ConversationRead.

## Reportes (`apps/reports`)

Dashboard (config JSON de widgets, compartido por áreas/roles/todos, versión), ReportSchedule
(frecuencia, hora local, día, turno, formatos, destinatarios, next_run_at), ReportRun (instantánea
JSON, data_version, formatos, estado, intentos; **único por (schedule, scheduled_for)**), ReportOutput.

## Hoja de cálculo (`apps/sheets`)

Workbook (data JSON con hojas/celdas/formatos/reglas, versión, propietario, área compartida,
dataset vinculado) y WorkbookVersion (copia por guardado, máx. 50).

## Documentos (`apps/documents`)

Folder, Document (StoredFile, etiquetas, carpeta, derived_from + operación y parámetros, info).

## Etiquetas (`apps/labels`)

LabelTemplate (borrador JSON `gpv-label/1` con revisión), LabelTemplateVersion (publicada e inmutable),
Printer (tipo, lenguaje, host/puerto o cola registrados por admin, DPI real, validada/habilitada),
SerialCounter (siguiente valor, prefijo, dígitos), PrintJob (versión de plantilla, impresora, ruta,
estado, cantidades, datos resueltos, seriales, idempotency_key único, reimpresión con motivo,
salidas PDF/ZPL, evidencia), PrintEvent (historial de estados).

## Kaizen (`apps/kaizen`)

Improvement (problema, estado actual, objetivo, área, responsable, prioridad, estado del flujo,
5 porqués, PDCA, vínculos a órdenes/reportes/evidencias, aprobación), KaizenAction, KaizenMeasure
(antes/después con periodos, unidad y fuente), KaizenSaving (fórmula, cálculo, aprobación),
KaizenTransition (historial).

## Formato de plantilla de etiqueta `gpv-label/1`

```json
{"schema": "gpv-label/1", "name": "Caja", "width_mm": 101.6, "height_mm": 76.2, "dpi": 203, "margin_mm": 2,
 "prompts": [{"name": "operador", "label": "Operador", "required": true}], "serial_counter": "",
 "elements": [{"id": "b1", "type": "code128", "x": 3, "y": 32, "w": 95, "h": 18, "rot": 0,
               "content": "{work_order}", "module_mm": 0.375, "show_text": true}]}
```

Tipos: `text`, `qr`, `code128`, `line`, `rect`, `image` (PNG incrustado). Contenido con
`{campo|transformación:arg}`; transformaciones permitidas: upper, lower, strip, strip_prefix,
strip_suffix, left, right, pad, replace, default, date.
