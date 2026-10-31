# Guía de implementación en servidor corporativo

> La instalación en infraestructura de GPV requiere autorización de TI. Esta guía describe lo necesario; no se realizó ninguna conexión ni cambio en servicios corporativos.

## 1. Requisitos del servidor

| Elemento | Recomendación inicial (200 empleados) |
|---|---|
| Sistema | Windows Server 2022 con IIS 10, o Linux (Ubuntu 24.04 / RHEL 9) con nginx |
| Runtime | **ASP.NET Core Hosting Bundle 10** (Windows) o `aspnetcore-runtime-10.0` (Linux) |
| CPU / RAM | 2–4 vCPU, 4–8 GB RAM (en prueba de carga la API usó ≤ 290 MB y ≤ 47 % de 4 núcleos con 200 usuarios virtuales) |
| Base de datos | SQL Server 2019+ o Azure SQL, con respaldos diarios y punto en el tiempo |
| Almacenamiento | Carpeta de datos con respaldo para adjuntos (≈10 MB máx. por archivo) |
| Red | HTTPS (certificado corporativo), **WebSockets habilitados** (Blazor Server y SignalR) |
| Identidad | Registros en Microsoft Entra ID (docs/CONFIGURACION_OUTLOOK.md) |
| Correo | Buzón compartido + permiso Graph `Mail.Send` acotado |

## 2. Publicación

```bash
dotnet publish src/GPV.ProductTimeFlow.Web -c Release -o out/web
dotnet publish src/GPV.ProductTimeFlow.API -c Release -o out/api     # solo si se usará la app móvil
```

### IIS (Windows)
1. Instale el Hosting Bundle .NET 10 y reinicie IIS.
2. Cree el sitio con un App Pool *Sin código administrado*, identidad dedicada con permisos de lectura en la carpeta de la app y escritura en `TimeFlow:DataRoot`.
3. Copie `out/web` y use `deployment/iis/web.config` como base. Habilite **WebSocket Protocol** en las características de IIS.
4. Defina las variables de entorno (ver `deployment/env.production.example`) en el App Pool o del sistema, nunca en archivos del sitio.
5. Enlace HTTPS con el certificado corporativo. Si se publica la API, use otro sitio o una aplicación virtual con su propio App Pool.

### Linux
1. Copie `out/web` a `/opt/gpv/timeflow/web`, cree el usuario `timeflow`.
2. `/etc/gpv/timeflow.env` (permisos 600) con las variables de producción.
3. `deployment/linux/timeflow-web.service` → `systemctl enable --now timeflow-web`.
4. nginx con TLS y WebSockets: `deployment/linux/nginx-timeflow.conf`.

### Varias instancias
Blazor Server requiere **afinidad de sesión** (sticky sessions) en el balanceador. Para SignalR entre servidores agregue Azure SignalR o backplane Redis. Las llaves de Data Protection deben compartirse (carpeta común o Key Vault). Active el procesador de correo en **una sola** instancia (`Email__ProcessorEnabled`); el reclamo con concurrencia evita duplicados incluso si se activa en varias.

## 3. Base de datos SQL Server

### Creación
1. Cree la base `GpvProductTimeFlow` y un login de aplicación con `db_datareader`, `db_datawriter` (y `db_ddladmin` solo durante migraciones).
2. Ejecute el script idempotente incluido: `deployment/sql/sqlserver-idempotent.sql` (puede reejecutarse sin daño). Para regenerarlo:
   ```bash
   dotnet tool restore
   cd src/GPV.ProductTimeFlow.Infrastructure
   dotnet ef migrations script --idempotent --context SqlServerTimeFlowDbContext -o ../../deployment/sql/sqlserver-idempotent.sql
   ```
3. `Database__Provider=SqlServer`, `Database__ConnectionString=...` (preferir autenticación integrada o identidad administrada), `Database__AutoMigrate=false`.
4. Al primer arranque se cargan catálogos (tipos, clasificaciones, festivos 2026–2027, parámetros). **No** se siembran datos DEMO en producción.

### Migrar de SQLite (DEMO) a SQL Server

Los datos DEMO son sintéticos y **no deben migrarse** a producción. El procedimiento recomendado es:

1. Producción arranca vacía con el script SQL (paso anterior).
2. Cargue empleados reales con **Administración → Empleados → Importar Excel** (plantilla descargable; primero «Validar (simulación)», luego «Confirmar»).
3. Revise el organigrama, roles y saldos de vacaciones con RH.
4. Configure festivos y parámetros de políticas.

Si TI decide trasladar datos de un piloto en SQLite, hágalo por tabla con una herramienta ETL (o `sqlite3 .dump` + transformación) respetando el orden de claves foráneas: Departments, Positions, Employees, Users, ReportingHierarchy, RequestTypes, LeaveCategories, Holidays, Requests, RequestPeriods, OvertimeRecords, ApprovalSteps, ApprovalDecisions, ElectronicSignatures, Attachments, VacationBalances, VacationTransactions, AdministrativeRegistrations, Notifications, EmailOutbox, ExcelExports, SystemSettings, FolioSequences y por último AuditLogs **conservando** `Sequence`, `PreviousHash` y `Hash` (si se alteran, la verificación de auditoría marcará la cadena como rota). Copie también la carpeta `attachments/`.

### Nuevas migraciones (desarrollo)
Cada cambio de modelo requiere migración para ambos proveedores:
```bash
cd src/GPV.ProductTimeFlow.Infrastructure
dotnet ef migrations add <Nombre> --context SqliteTimeFlowDbContext   --output-dir Persistence/Migrations/Sqlite
dotnet ef migrations add <Nombre> --context SqlServerTimeFlowDbContext --output-dir Persistence/Migrations/SqlServer
```

## 4. Lista de verificación de salida a producción

- [ ] Autorización de TI y de Seguridad de la Información; revisión de privacidad (datos personales).
- [ ] Registros de Entra ID (Web, API, correo) con consentimiento y alcance restringido.
- [ ] Certificado TLS corporativo; HSTS activo; WebSockets habilitados.
- [ ] SQL Server con respaldos y prueba de restauración; cadena de conexión fuera de archivos.
- [ ] Variables de entorno de producción cargadas; `TimeFlow__Mode=Production` (la app valida la configuración al arrancar).
- [ ] Importación de empleados reales y validación de jerarquías con Producto.
- [ ] Parámetros de vacaciones, tiempo extra y festivos validados con RH.
- [ ] Prueba de envío de correo con Graph a buzones de prueba.
- [ ] Prueba de carga en infraestructura representativa (scripts incluidos) y registro de resultados.
- [ ] Monitoreo de logs (`DataRoot/logs`, o sink de Serilog corporativo) y alertas de correos fallidos.
- [ ] Definición de retención y depuración de expedientes con Jurídico/RH.
