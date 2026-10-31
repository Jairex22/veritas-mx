# Documentación técnica · GPV Product TimeFlow 4.0.0

## 1. Arquitectura

Clean Architecture pragmática sobre .NET 10:

```
Shared  ←  Domain  ←  Application  ←  Infrastructure  ←  Web (Blazor Server, PWA)
   ↑                                                  ←  API (REST, JWT/Entra ID)
   └──────────────────────────────────────────────────── Mobile (MAUI Blazor Hybrid, vía API)
```

| Proyecto | Responsabilidad | Dependencias externas |
|---|---|---|
| Shared | Enums de contrato, DTOs, etiquetas en español, `TimeFlowApiClient` | ninguna |
| Domain | Entidades, `RequestStateMachine`, cálculos (tiempo extra, días hábiles, antigüedad), hashes | ninguna |
| Application | Casos de uso, autorización por recurso, validaciones, outbox de notificaciones, puertos | EF Core (abstracciones) |
| Infrastructure | `TimeFlowDbContext` (SQLite/SQL Server), Graph, PDF (MigraDoc), Excel (ClosedXML), QR, almacenamiento, servicios en segundo plano, seed | ver README |
| Web | UI Blazor Interactive Server, cookies/OIDC, descargas, hub SignalR | Microsoft.Identity.Web, Serilog |
| API | Minimal APIs v1, OpenAPI, JWT DEMO / Entra ID, rate limiting | idem |

**Decisión clave:** la Web invoca los servicios de Application en proceso (sin HTTP interno); la API expone los mismos servicios. Un único conjunto de reglas para todos los canales.

En Blazor Server cada operación se ejecuta en un ámbito DI nuevo (`ServiceRunner`) para no compartir un `DbContext` entre operaciones concurrentes del mismo circuito.

## 2. Máquina de estados (fuente única de verdad)

`src/GPV.ProductTimeFlow.Domain/RequestStateMachine.cs`. Cualquier combinación no listada lanza `InvalidTransitionException` (HTTP 409).

| Desde | Acción | Hacia | Ejecuta |
|---|---|---|---|
| Draft / ReturnedForCorrection | Submit | Submitted | Solicitante |
| Submitted | RouteToSupervisor | PendingSupervisor | Sistema (misma transacción) |
| PendingSupervisor | SupervisorApprove / Reject / Return | SupervisorApproved / SupervisorRejected / ReturnedForCorrection | Jefa directa asignada |
| SupervisorApproved | RouteToManager | PendingManager | Sistema |
| PendingManager | ManagerApprove / Reject / Return | ManagerApproved / ManagerRejected / ReturnedForCorrection | Jefe superior asignado |
| ManagerApproved | RouteToAdministrative | PendingAdministrativeRegistration | Sistema |
| PendingAdministrativeRegistration / AdministrativeObserved | AdministrativeObserve | AdministrativeObserved | Registro administrativo |
| PendingAdministrativeRegistration / AdministrativeObserved | AdministrativeRegister | AdministrativeRegistered | Registro administrativo |
| AdministrativeRegistered | Complete | Completed | Registro administrativo |
| Draft / PendingSupervisor / ReturnedForCorrection / PendingManager | Cancel | Cancelled | Solicitante |

Terminales: SupervisorRejected, ManagerRejected, Completed, Cancelled. «Marcar como recibido» es un acuse sin cambio de estado (`AdministrativeReceive`). Etiquetas en español: `Shared/Labels.cs`.

### Protocolo de cada acción (`WorkflowService`)
1. **Identidad**: `ActorGuard` verifica en BD que la cuenta y el empleado estén activos.
2. **Permisos**: solo el asignado del filtro vigente (instantánea de jerarquía tomada al enviar); nadie autoriza lo propio; jefa y jefe deben ser distintos.
3. **Estado**: tabla de transiciones.
4. **Reglas**: revalidación completa (saldo, traslapes, límites); `ExpectedVersion` debe coincidir con la versión revisada; firma + consentimiento para aprobar; justificación ≥10 caracteres para rechazar/devolver; integridad del hash de contenido.
5. **Transición atómica**: transacción explícita; token de concurrencia `ConcurrencyStamp` en `Requests` (y renovado cuando cambian pasos, decisiones o firmas).
6. **Auditoría** encadenada.
7. **Notificación pendiente**: `Notifications` + `EmailOutbox` en la misma transacción.
8. **Confirmación**: `WorkflowResultDto`.
9. **Interfaz**: tras el commit se empuja el aviso por SignalR y el bus en proceso; las pantallas abiertas se recargan.

### Idempotencia y concurrencia
- Cada envío/decisión lleva `IdempotencyKey` (cuerpo o cabecera `Idempotency-Key`), con índice único `(RequestId, IdempotencyKey)`. Repetir la clave devuelve `WasDuplicate=true` sin aplicar nada.
- Dos decisiones simultáneas con claves distintas: una gana; la otra recibe 409 (`DbUpdateConcurrencyException` o estado ya cambiado). Verificado en pruebas de integración y en la prueba de carga (0 dobles aprobaciones).
- Descuento de vacaciones: transacción `Consumption` con clave única `consume:{requestId}`.
- Folios `TF-AAAA-NNNNNN` desde `FolioSequences` con token de concurrencia e índice único.

### Versiones y firmas
- `Version` aumenta cuando cambia contenido sustantivo de una solicitud ya revisada (edición tras devolución, adjuntos) y en cada reenvío sin edición previa. Todas las firmas vigentes se invalidan con motivo y fecha.
- `ContentHash` = SHA-256 del contenido canónico (fechas, horas, motivo, justificación, clasificación, proyecto, actividad, hashes de adjuntos, versión).
- `ElectronicSignature` guarda imagen PNG, `DocumentHash` (= ContentHash firmado), `SignatureHash` = SHA-256(imagen | documento | firmante | solicitud | versión | fecha), IP y agente. No se pueden modificar (solo invalidar); una firma no puede reutilizarse para otra solicitud ni otra versión.
- **Firma electrónica simple**: trazo capturado tras autenticación. **No** es firma electrónica avanzada ni firma digital criptográfica con certificado (e.firma/X.509). Si se requiere valor probatorio reforzado, ver pendientes.

## 3. Modelo de datos

Tablas (EF Core, migraciones separadas por proveedor en `Infrastructure/Persistence/Migrations/{Sqlite,SqlServer}`):

`Departments, Positions, Employees, Users, ReportingHierarchy, RequestTypes, LeaveCategories, Holidays, Requests, RequestPeriods, OvertimeRecords, ApprovalSteps, ApprovalDecisions, ElectronicSignatures, Attachments, VacationBalances, VacationTransactions, Notifications, EmailOutbox, AuditLogs, AdministrativeRegistrations, ExcelExports, SystemSettings, FolioSequences`.

- Claves foráneas con `Restrict` para preservar historial (las solicitudes nunca se eliminan físicamente).
- Índices únicos: número de empleado, correo normalizado, folio, `(EmployeeId, PeriodYear)` en saldos, claves de deduplicación, `(RequestId, RequestVersion, Type)` en pasos, `Sequence` en auditoría.
- Índices de consulta: bandejas `(AssignedSupervisorId, Status)`, `(AssignedManagerId, Status)`, `(Status, StatusChangedAtUtc)`, periodos `(StartDate, EndDate)`, notificaciones por destinatario.
- Restricciones CHECK: horas/días ≥ 0, `EndDate ≥ StartDate`, horas de tiempo extra > 0, versión ≥ 1.
- Fechas en UTC (`DateTime` con conversión a `Kind=Utc`); fechas de calendario con `DateOnly`/`TimeOnly`; zona `America/Mexico_City` para presentación.
- Inmutabilidad a nivel de aplicación: `AuditLogs`, `ApprovalDecisions` y `VacationTransactions` no admiten UPDATE/DELETE (excepción en `SaveChanges`).
- Auditoría encadenada: `Hash = SHA-256(PreviousHash | Sequence | fecha | actor | acción | entidad | detalle | IP)`. `AuditService.VerifyAsync` recorre la cadena y detecta modificaciones, inserciones o eliminaciones (probado alterando un registro con SQL directo). Para inmutabilidad a nivel de base, en SQL Server se recomienda además revocar UPDATE/DELETE al login de la app sobre `AuditLogs` o usar tablas *ledger*.

## 4. Seguridad (OWASP ASVS)

| Control | Implementación |
|---|---|
| Autenticación | Entra ID (OIDC/JWT) en producción; DEMO: PBKDF2-HMAC-SHA512 100 000 iteraciones, bloqueo 5 intentos/15 min, tiempo constante para cuentas inexistentes |
| Sesión | Cookie `__Host-`, HttpOnly, Secure, SameSite=Strict, 8 h deslizante; revalidación de `SecurityStamp` en cada petición (cambio de rol o baja revoca sesiones) |
| Autorización | Por rol (`[Authorize(Roles=…)]`) y **por recurso** en Application (`RequestAccess.VisibleTo/CanView`); recursos ajenos responden **404** (anti-IDOR/enumeración); IDs de solicitudes y adjuntos son GUID |
| CSRF | Antiforgery de Blazor/ASP.NET Core en formularios; la API usa bearer (no cookies) |
| XSS | Razor codifica por defecto; CSP `script-src 'self'` sin scripts en línea; plantillas de correo con `HtmlEncode`; vista previa de correo aislada en iframe `sandbox` con CSP propia |
| Inyección SQL | EF Core parametrizado; sin SQL dinámico |
| Inyección de fórmulas Excel | Textos que inician con `= + - @ tab CR` se guardan con *QuotePrefix* (probado) |
| Adjuntos | Lista blanca (PDF, PNG, JPG, DOCX, XLSX), verificación de *magic bytes*, 10 MB, máx. 10 por solicitud, nombre aleatorio en disco, protección contra *path traversal*, SHA-256 |
| Fuerza bruta / abuso | Rate limiting en login (por IP) y API (por usuario); bloqueo de cuenta |
| Cabeceras | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, COOP, HSTS fuera de desarrollo |
| Secretos | Ninguno en el repositorio ni en el ZIP; variables de entorno / almacén seguro |
| Logging | Serilog estructurado, sin cuerpos de petición ni contraseñas; errores devuelven ProblemDetails sin trazas |
| Separación de ambientes | Validación de arranque en `Production`; franja y asunto `[DEMO]` en ambientes no productivos |
| Privacidad | Compañeros sin relación de mando ven «Ausencia en el equipo» sin nombre ni motivo; verificación QR pública sin datos personales |

## 5. API REST v1 (resumen)

Base `/api/v1`, JSON con enums como texto, errores `application/problem+json` (422 validación con `errors[]`, 409 conflicto, 404 no encontrado/sin permiso, 403, 401, 423 cuenta bloqueada, 429).

| Método y ruta | Descripción |
|---|---|
| `POST /auth/login` | Login DEMO → JWT (no existe en modo Entra ID) |
| `GET /me`, `GET /dashboard`, `GET /search?term=` | Perfil, tablero por rol, búsqueda |
| `GET /requests?scope=Mine\|ApprovalInbox\|TeamHistory\|Administrative\|All&status&kind&from&to&search&bucket&page&pageSize` | Listado paginado |
| `GET/PUT /requests/{id}`, `POST /requests` | Expediente, edición, borrador |
| `POST /requests/{id}/submit\|decision\|administrative\|cancel` | Flujo (admite `Idempotency-Key`) |
| `POST/DELETE /requests/{id}/attachments[/{aid}]`, `GET /attachments/{id}` | Adjuntos |
| `GET /requests/{id}/pdf` | Expediente PDF |
| `GET /vacations/balance`, `POST /vacations/preview`, `POST /overtime/preview`, `GET /overtime/summary` | Saldos y cálculos |
| `GET /calendar?from&to&scope` | Calendario |
| `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all` | Avisos |
| `GET /exports/requests.xlsx?set&kind&employeeId&from&to` | Excel |
| `/admin/employees[...]`, `/admin/employees/import`, `/admin/settings/policy`, `/admin/audit[/verify]`, `/admin/emails`, `/admin/health` | Administración de Producto |
| `GET /verify/{folio}?c=` | Verificación pública del QR |

Documento OpenAPI: `/openapi/v1.json` (deshabilitado en producción). Hub SignalR: `/hubs/notifications`, evento `notification`.

## 6. Reglas de negocio configurables (`SystemSettings`, prefijo `Policy.`)

Mínimo/máximo de horas por solicitud y por mes, días hacia atrás permitidos, anticipación máxima, días hábiles, máximo de días consecutivos de vacaciones, saldo negativo, horas para recordatorio y urgencia, buzón administrativo, firma obligatoria del solicitante, color corporativo, leyenda del PDF, retención. Días de vacaciones por antigüedad: tabla de referencia LFT 2023 en `VacationEntitlementPolicy` (solo sugerencia al dar de alta; el saldo oficial se ajusta en coordinación con RH). Ningún cálculo de nómina se realiza en la aplicación.

## 7. Rendimiento

Paginación en todos los listados (máx. 100), proyecciones con `AsNoTracking`, `AsSplitQuery` en expedientes, índices de bandeja, cálculo de agregados decimales en memoria (compatibilidad SQLite). Resultados medidos: ver TEST_RESULTS.md.
