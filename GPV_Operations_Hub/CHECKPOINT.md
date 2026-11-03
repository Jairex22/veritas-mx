# Checkpoint del proyecto

Versión: **1.1.0** · Fecha: 2026-11-03 · Rama: `claude/great-shannon-y0f3cd`

## Diagnóstico inicial (al recibir el requerimiento del portal del turno)

* Base existente v1.0.1 (Django 5.2 LTS) funcional: permisos por capacidad y área, auditoría,
  notificaciones internas, cola de trabajos, planificador con *lease*, exportadores PDF/XLSX,
  etiquetas con consecutivos transaccionales, Kaizen. 72 pruebas verdes.
* No existía: contexto de estación/turno, modelo de eventos con origen y conciliación, conector OData,
  captura de paros/ayudas/materiales, reporte de turno, relevo.
* Bloqueado por dependencia externa: acceso a FactoryLogix (URL, cuenta, `$metadata`). Se implementó
  la interfaz completa y su diagnóstico, y se probó contra un servicio **simulado**.

## Matriz requisito / estado / evidencia

| Requisito (sección del encargo) | Estado | Evidencia |
|---|---|---|
| 3 · Mi turno: contexto, QR de estación, 4 acciones, siguiente acción, sin cambio silencioso, vistas por rol | Hecho | `MyShiftTests`, E2E `e2e_shift.js` |
| 4 · Conector OData backend de solo lectura, diagnóstico por etapas, auth real, paginación, `$select`, incremental/ventana, upsert, reintentos, estado de fuente | Hecho (probado con simulado) | `ODataTests`; conexión real **pendiente de GPV** |
| 4 · Captura web y conciliación (80+80=80; dos lotes=160; ambiguo → revisión) | Hecho | `CountingTests` |
| 5 · Operación de conteo, Top/Bottom, retests, FPY, paneles con factor confirmado, snapshot, consulta por serie | Hecho | `CountingTests`, `test_serial_lookup…` |
| 6 · Reporte SMT del turno, estados, borrador por proceso, medianoche, descansos, revisiones, una vez por periodo, PDF/Excel | Hecho | `ReportTests` |
| 7 · Relevo digital (recibir ≠ cerrar) | Hecho | `test_handover_receipt_does_not_close_incidents` |
| 8 · Ayuda con motivos, ruta a grupos, estados, duplicados, recordatorio/escalamiento interno; paros con corrección | Hecho | `FloorTests` |
| 9 · Solicitud de material sin inventario | Hecho | `test_material_request_is_not_inventory` |
| 10 · Instrucciones con revisión vigente/obsoleta; listas con pendientes; leer ≠ capacitar | Hecho | `test_instructions_only_approved…` |
| 11 · Etiquetas desde contexto, Enter no imprime, sin duplicar trabajos/consecutivos | Hecho | `test_label_from_context…`, E2E |
| 12 · Observación vs disposición; Kaizen desde repetidos; tablero; pantalla de área | Hecho | `FloorTests`, E2E |
| 13 · Estados de guardado, cola sin red de bajo riesgo (ayudas) idempotente, recuperación sin duplicar | Hecho (cola solo para ayudas) | `test_offline_json_resend_is_idempotent`, `ReportTests` |
| 14 · Configuración con permisos e historial, diagnóstico de servicio/fuente/espacio, respaldo | Hecho | `apps/shift/admin.py`, `gpv_diagnose`, `test_backup.py` |
| Inicio local 127.0.0.1, sin firewall, comportamiento al suspender | Hecho; **no ejecutado en Windows** | `INICIAR.bat`, `RESPALDO_RESTAURACION_Y_SOPORTE.md` |
| 15 · Criterios 1–28 | Ver `PRUEBAS_Y_RESULTADOS.md` | |

## Pendiente (requiere GPV)

Ver `DECISIONES_PENDIENTES.md`: línea/estaciones/operación de conteo/turno reales, acceso OData
(URL, autenticación, cuenta de lectura, `$metadata`), grupos y motivos oficiales, validación física
de etiquetas, ejecución en el equipo Windows del piloto y prueba con personal real.

## Cómo continuar

1. `GPV_ENV=test python manage.py test` (121 pruebas) y `tools/e2e_shift.js` con `seed_demo` +
   `tools/fake_odata_server.py`.
2. Al recibir el `$metadata` real: registrar la conexión, diagnosticar, mapear y sincronizar; ajustar
   `refresh_seconds` tras medir la carga real.
3. Si el volumen real supera ~10 000 eventos por turno en la operación de conteo, considerar agregar
   en SQL o en caché `shift_summary` (medición en `PRUEBAS_Y_RESULTADOS.md`).
