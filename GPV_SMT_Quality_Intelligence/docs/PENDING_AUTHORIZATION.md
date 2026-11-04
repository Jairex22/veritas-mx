# Funciones pendientes de autorización o validación

| # | Elemento | Responsable | Estado |
|---|---|---|---|
| 1 | Habilitar modo real (`security.live_mode_approved`) | TI / MES | Pendiente |
| 2 | Canal cifrado (HTTPS o proxy corporativo) para Basic Auth, o mecanismo de autenticación alternativo | TI | Pendiente — Basic sobre HTTP bloqueado por defecto |
| 3 | Validar `$metadata` real (tipos de Quality/QualityHistory, versión OData) | MES | Pendiente — usar Diagnóstico → Probar $metadata |
| 4 | Medir tiempos reales por entidad con consultas mínimas | MES | Pendiente |
| 5 | Production Pulse con actualización automática (5 min) | TI | Desactivado (`pulse.auto_refresh_enabled = false`) |
| 6 | ProductivityOverTime | MES | Excluido (timeouts observados); no está en la lista blanca |
| 7 | Definir turnos (`pulse.shifts`) | Producción | Pendiente |
| 8 | Flujos de proceso autorizados por ensamble (`rework.process_flows`) para confirmar bucles | Ingeniería de procesos | Pendiente |
| 9 | Fuente de aprobación final (PASS) de la unidad (p. ej. otra entidad de test) | MES | Pendiente de integración: contrato `final_result` existe, hoy siempre `NO_VERIFICABLE` |
| 10 | Confirmar zona horaria de `DefectHistoryTime` / `DateCreated` | MES | Pendiente (ver alerta R09) |
| 11 | Exportación PDF/XLSX con librerías externas | TI | No requerido (XLSX nativo; PDF vía impresión) |
| 12 | Pruebas de carga contra FactoryLogix | TI / MES | No ejecutadas — requieren autorización |
| 13 | Uso en red (no loopback) | TI | No aprobado; servidor en 127.0.0.1 |
