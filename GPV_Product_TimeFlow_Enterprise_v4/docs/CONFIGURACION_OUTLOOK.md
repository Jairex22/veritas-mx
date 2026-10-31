# Configuración de Outlook / Microsoft 365 (Microsoft Graph) y Microsoft Entra ID

> **Estado:** la integración está **implementada pero no probada contra un tenant real**: no se contó con credenciales corporativas durante la entrega. En DEMO/TEST se usa el proveedor **Mock**, que **no envía** correos: guarda cada mensaje como HTML en `App_Data/mail-drop/` y lo marca «Registrado en buzón DEMO (no enviado)» (`MockDelivered`), nunca «Enviado». Ninguna prueba modificó servicios corporativos.

## 1. Cómo funciona el envío

1. Cada transición del flujo genera, **en la misma transacción**, el aviso interno y el mensaje en la tabla `EmailOutbox` (patrón Outbox). Si la transacción falla no queda ningún correo huérfano.
2. Cada mensaje tiene una **clave de deduplicación única** (`{solicitud}:{evento}:v{versión}:{destinatario}`): el mismo aviso nunca se encola dos veces.
3. `EmailOutboxProcessor` (servicio en segundo plano de la Web) reclama los mensajes con un token de concurrencia (dos instancias nunca envían el mismo) y llama a `GraphEmailSender`.
4. Si falla: reintentos con espera exponencial (15 s · 2ⁿ, máx. 1 h) hasta `Email:MaxAttempts` (6). Después queda en estado `Fallido`, visible en **Administración → Correos**, donde puede reintentarse.
5. `ReminderBackgroundService` encola recordatorios diarios de solicitudes pendientes más de `ReminderAfterHours`.

### Eventos y destinatarios

| Evento | Destinatario |
|---|---|
| Empleado envía | Jefa directa |
| Jefa aprueba | Jefe superior |
| Jefa rechaza / devuelve | Empleado |
| Jefe superior aprueba | Buzón de registro administrativo (configurable en *Configuración → Políticas*) |
| Jefe superior rechaza | Empleado (CC jefa directa) |
| Jefe superior devuelve | Empleado |
| Registro administrativo registra | Empleado |
| Solicitud completada | Empleado (confirmación final) |
| Pendiente > N horas | Responsable del filtro vigente (recordatorio diario) |

Contenido: folio, empleado, tipo, fechas, duración, motivo resumido (≤120 caracteres), estado, responsable y **enlace al expediente**. No incluye justificaciones completas, adjuntos ni datos personales adicionales; las acciones se realizan dentro de la aplicación tras autenticarse. Plantilla: `src/GPV.ProductTimeFlow.Infrastructure/Email/Templates/notification.html` (todos los valores se codifican en HTML).

## 2. Registro de aplicación para correo (tarea de TI)

1. **Microsoft Entra admin center → App registrations → New registration**: nombre `GPV TimeFlow Mail Sender`, cuentas solo de este directorio, sin URI de redirección.
2. **API permissions → Microsoft Graph → Application permissions → `Mail.Send`** → *Grant admin consent*.
3. **Restringir el alcance** (obligatorio): sin restricción, `Mail.Send` de aplicación puede enviar como cualquier buzón. Use una de estas opciones:
   - **RBAC for Applications de Exchange Online** (recomendado actualmente), con un ámbito de administración limitado al buzón remitente; o
   - **Application Access Policy** (`New-ApplicationAccessPolicy -AppId <ClientId> -PolicyScopeGroupId timeflow-senders@dominio -AccessRight RestrictAccess`).
4. Cree un **buzón compartido** remitente, p. ej. `timeflow@dominio`, sin licencia ni inicio de sesión interactivo.
5. **Credencial**: preferentemente un **certificado** (`Certificates & secrets → Certificates`). Un secreto de cliente también funciona, pero caduca y es más fácil de filtrar.

## 3. Configuración de la aplicación (sin secretos en archivos)

Variables de entorno del servidor (o Azure Key Vault / almacén aprobado):

```
Email__Provider=Graph
Email__ProcessorEnabled=true                 # solo en la instancia Web
Email__Graph__TenantId=<tenant-id>
Email__Graph__ClientId=<client-id>
Email__Graph__CertificatePath=D:/GPV/TimeFlow/certs/timeflow-mail.pfx
Email__Graph__CertificatePassword=<desde almacén seguro>
#   o bien  Email__Graph__ClientSecret=<secreto>
Email__Graph__SenderMailbox=timeflow@dominio
TimeFlow__PublicBaseUrl=https://timeflow.dominio
```

La aplicación **no almacena contraseñas de Outlook** ni usa autenticación básica: emplea OAuth 2.0 *client credentials* (`ClientCertificateCredential` / `ClientSecretCredential` de Azure.Identity) y `POST /users/{buzón}/sendMail`.

### Verificación posterior (pendiente, requiere TI)

1. Arrancar en TEST con `Email__Provider=Graph` y un buzón de prueba como destinatario (cambie el correo del empleado de prueba).
2. Enviar una solicitud y comprobar en *Administración → Correos* el estado «Enviado (Microsoft Graph)».
3. Revisar la bandeja de Elementos enviados del buzón remitente (si `SaveToSentItems=true`).
4. Revocar temporalmente el permiso para verificar reintentos y el estado «Fallido».

## 4. Inicio de sesión con Microsoft Entra ID (Web y API)

### Web (OpenID Connect)
1. Registro de aplicación `GPV TimeFlow Web`, tipo **Web**, redirect URI `https://timeflow.dominio/signin-oidc`, front-channel logout `https://timeflow.dominio/signout-callback-oidc`.
2. Habilitar *ID tokens*. Credencial (certificado o secreto) para el flujo de código.
3. Asignar usuarios: *Enterprise applications → Properties → Assignment required = Yes* y agregar el grupo de Producto y aprobadores.
4. Variables: `Authentication__Mode=EntraId`, `AzureAd__TenantId`, `AzureAd__ClientId`, `AzureAd__ClientSecret` (o certificado según Microsoft.Identity.Web).

### API (bearer)
1. Registro `GPV TimeFlow API`, *Expose an API* → `api://<client-id>` con el scope `access_as_user`.
2. Variables: `Authentication__Mode=EntraId`, `AzureAd__TenantId`, `AzureAd__ClientId`, `AzureAd__Audience=api://<client-id>`.
3. La app móvil necesitará MSAL.NET con el scope anterior (pendiente; ver docs/PENDIENTES_Y_DEPENDENCIAS.md).

### Vinculación con empleados
Al iniciar sesión, TimeFlow busca al empleado por `oid` (Object ID) o por el correo `preferred_username`. Si no existe o está inactivo, se rechaza el acceso. La primera vez guarda el `oid` en `Users.ExternalObjectId`. Los roles se administran en TimeFlow (*Administración → Empleados*), no en Entra ID.
