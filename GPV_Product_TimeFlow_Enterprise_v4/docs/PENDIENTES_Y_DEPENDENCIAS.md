# Pendientes y dependencias corporativas

## A. Dependencias de TI / Microsoft 365 (requieren autorización)

| # | Dependencia | Estado en la entrega | Qué se necesita |
|---|---|---|---|
| 1 | Microsoft Entra ID (Web y API) | Código implementado (Microsoft.Identity.Web), **no probado con tenant real** | Registros de aplicación, consentimiento, asignación de usuarios |
| 2 | Envío de correo con Microsoft Graph | Implementado (`GraphEmailSender`), **no probado con tenant real**; DEMO usa Mock | Buzón remitente, permiso `Mail.Send` acotado (RBAC/Application Access Policy), certificado |
| 3 | Servidor corporativo (IIS o Linux) y certificado TLS | Plantillas en `deployment/` | Servidor aprobado, DNS, certificado, WebSockets |
| 4 | SQL Server | Migraciones y script idempotente generados; **no ejecutados contra SQL Server** (solo se compilaron) | Instancia, login de aplicación, respaldos |
| 5 | Carpeta de adjuntos con respaldo | Almacenamiento local implementado | Ruta en servidor o recurso compartido / Blob |
| 6 | Identidad visual oficial de GPV | Color configurable; logotipo no incluido | Recursos de marca autorizados |
| 7 | Formatos oficiales de RH | PDF con plantilla propia (MigraDoc) | Formato oficial para adaptar `PdfRenderer` |

## B. Dependencias de RH / políticas internas

- Tabla de días de vacaciones por antigüedad, periodo vacacional (calendario vs. aniversario), vigencia y acumulación. Hoy: saldo por **año calendario** con asignación sembrada para el año actual y el siguiente. La asignación de periodos futuros se hace con *Ajustar vacaciones*; **falta un proceso automático de asignación anual**.
- Topes de tiempo extra, elegibilidad y reglas de pago (la app solo registra horas; no calcula nómina).
- Catálogo definitivo de clasificaciones de permisos y documentos exigidos.
- Calendario oficial de días festivos de cada año.
- Política de retención y depuración de expedientes (hay parámetro, pero no hay purga automática).

## C. Pendientes técnicos (no implementados o no verificados)

| Pendiente | Detalle |
|---|---|
| App móvil sin compilar | El proyecto MAUI está completo y su código Razor/C# se validó contra los contratos reales en un proyecto auxiliar, pero **no se compiló como MAUI ni se generó APK/IPA** (sin workload MAUI, Android SDK ni Xcode en el entorno). Ver `src/GPV.ProductTimeFlow.Mobile/README.md` |
| Entra ID en móvil | La app móvil usa el login DEMO de la API; en producción requiere MSAL.NET y el scope de la API |
| Reasignación/delegación de aprobadores | Si una jefa está ausente, hoy se cambia la jerarquía para solicitudes nuevas; las solicitudes en trámite conservan a su aprobador. Falta una función de delegación/reasignación auditada |
| Firma digital avanzada | Solo firma electrónica simple. Si se requiere firma avanzada o e.firma (certificados X.509, sello de tiempo), se necesita un proveedor certificado |
| Inmutabilidad a nivel de BD | La auditoría es inmutable a nivel de aplicación con detección por hash. En SQL Server, revocar UPDATE/DELETE sobre `AuditLogs` o usar *ledger tables* |
| Escalamiento horizontal | Varias instancias requieren sticky sessions, backplane de SignalR (Azure SignalR/Redis) y llaves de Data Protection compartidas |
| Carga en infraestructura representativa | La prueba de 200 usuarios virtuales se hizo en el contenedor de desarrollo con SQLite; repetirla en el servidor y con SQL Server |
| Notificaciones push móviles | No implementadas (FCM/APNs); la app móvil usa SignalR + sondeo |
| Contratos para móvil | Recomendaciones: unificar la serialización de enums en el hub SignalR (hoy numérica) con REST (texto); agregar al `TimeFlowApiClient` los métodos de «marcar todo como leído» y eliminar adjunto (hoy son extensiones en Mobile); exponer el modo de ambiente sin autenticación; refresh tokens |
| Accesibilidad | Diseño orientado a WCAG 2.2 AA (contraste, foco visible, etiquetas ARIA, tablas alternativas a gráficos, objetivos táctiles ≥ 40 px), **sin auditoría formal** con lector de pantalla |
| Safari / Firefox / iPhone | Las pruebas automatizadas usaron Chromium. Falta verificación manual en Safari (iOS/macOS) y Firefox |
| Eliminar borradores | No hay eliminación de borradores (se cancelan) |

## D. Riesgos conocidos

- 200 inicios de sesión **simultáneos** con cuentas locales tardan ~5 s (PBKDF2 limitado por CPU, deliberado contra fuerza bruta). En producción el inicio de sesión lo realiza Entra ID.
- SQLite es solo para DEMO y desarrollo: escrituras concurrentes intensas de varios procesos pueden esperar el bloqueo de la base.
