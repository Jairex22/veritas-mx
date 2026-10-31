# GPV Product TimeFlow — App móvil (.NET MAUI Blazor Hybrid)

App móvil de **GPV Product TimeFlow Enterprise v4.0.0** para Android e iOS. Sirve para solicitar tiempo extra,
vacaciones y permisos con o sin goce de sueldo, y para autorizarlos en el flujo de tres filtros
(empleado → jefa directa → jefe superior → registro administrativo).

> **Importante: este proyecto NO se compiló en el entorno donde se entregó.** Ese entorno era Linux con el SDK
> de .NET 10.0.114 de Ubuntu (compilado desde fuente), que no puede instalar los workloads de MAUI. Tampoco había
> Android SDK ni Xcode. Revisa la sección [Estado de verificación](#estado-de-verificación) antes de distribuir la app.

- La interfaz completa está en español de México y es una app Blazor (Razor) dentro de un `BlazorWebView`.
- Solo consume la API REST existente, mediante el cliente tipado `TimeFlowApiClient` de
  `GPV.ProductTimeFlow.Shared`. No referencia Domain, Application ni Infrastructure.
- **No forma parte de `GPV.ProductTimeFlow.sln`.** Así `dotnet build` en la raíz sigue funcionando sin MAUI.
  Este proyecto se compila por separado (ver abajo).

---

## Prerrequisitos

| Herramienta | Versión |
|---|---|
| .NET SDK | 10.0.1xx **oficial de Microsoft** (no el de los repositorios de Ubuntu; ese no admite workloads) |
| Workloads | `dotnet workload install maui-android maui-ios` (en Windows sin Mac basta `maui-android`) |
| IDE | Visual Studio 2022 17.14 o posterior (o Visual Studio 2026) con la carga de trabajo *.NET Multi-platform App UI*; o VS Code con la extensión **.NET MAUI** (C# Dev Kit) |
| Android | Android SDK Platform 35 (API 35), Build-Tools 35, un emulador x86_64/arm64 con imagen Google APIs |
| Java | JDK 17 (Microsoft OpenJDK 17 recomendado) |
| iOS | macOS con la versión de Xcode que exija el workload de iOS de .NET 10, más una cuenta de Apple Developer para firmar |

Para comprobar la instalación:

```bash
dotnet --info                 # debe listar maui-android (y maui-ios en macOS)
dotnet workload list
```

Si el SDK de Android no está en la ruta por defecto, indica dónde está:
`-p:AndroidSdkDirectory=/ruta/android-sdk -p:JavaSdkDirectory=/ruta/jdk-17`.

---

## Estructura

```
src/GPV.ProductTimeFlow.Mobile/
├── GPV.ProductTimeFlow.Mobile.csproj   # net10.0-android (+ net10.0-ios fuera de Linux)
├── MauiProgram.cs                      # DI: BlazorWebView, ServerSettings, TimeFlowApi, AuthState, NotificationCenter…
├── App.xaml / MainPage.xaml            # BlazorWebView → wwwroot/index.html, RootComponent = Components.Routes
├── Components/
│   ├── Routes.razor                    # Router + protección de páginas (sesión) + restauración de sesión
│   ├── TimeFlowComponentBase.cs        # Busy, errores (ApiException.Errors), 401 → cierre de sesión
│   ├── Layout/                         # MainLayout (barra superior + campana), BottomNav, BlankLayout
│   ├── Pages/                          # Login, Inicio, Solicitudes, Nueva/Editar, Detalle, Calendario, Vacaciones, Notificaciones, Más, Ajustes
│   └── Ui/                             # StatusChip, RequestCard, SignaturePad, BottomSheet, previews, etc.
├── Services/
│   ├── ServerSettings.cs               # URL del servidor (Preferences) y validación HTTP/HTTPS
│   ├── TimeFlowApi.cs                  # HttpClient + TimeFlowApiClient; se reconstruye al cambiar de servidor
│   ├── AuthState.cs                    # JWT y perfil en SecureStorage, restauración y cierre por 401
│   ├── NotificationCenter.cs           # SignalR /hubs/notifications + sondeo cada 60 s
│   ├── DeviceFiles.cs                  # FilePicker (adjuntos) y Launcher (abrir PDF/adjuntos)
│   └── TimeFlowApiClientExtensions.cs  # 2 endpoints existentes que aún no expone TimeFlowApiClient
├── wwwroot/  index.html · css/app.css · js/signature.js
├── Platforms/Android/  MainActivity, MainApplication, AndroidManifest.xml, Resources/xml/network_security_config.xml
├── Platforms/iOS/      AppDelegate, Program, Info.plist, Entitlements.plist, PrivacyInfo.xcprivacy
└── Resources/          AppIcon (appicon.svg + appiconfg.svg), Splash (splash.svg)
```

Windows y Mac Catalyst se dejaron fuera a propósito para que el proyecto sea más simple. Para añadir Windows, agrega
`net10.0-windows10.0.19041.0` en `TargetFrameworks` (con la condición `IsOSPlatform('windows')`), además de
`Platforms/Windows` (App.xaml, Package.appxmanifest) y `WindowsPackageType=None`.

---

## Ejecutar contra la API local (DEMO)

### 1. Levantar la API

Desde la raíz del repositorio:

```bash
dotnet run --project src/GPV.ProductTimeFlow.API --launch-profile http
```

- Usa el perfil **`http`**. Escucha solo en `http://localhost:5201`.
- No uses el perfil por defecto (`https`): la API tiene `UseHttpsRedirection`, así que redirigiría a
  `https://…:7201` con el certificado de desarrollo, y el emulador no confía en ese certificado.
- Las cuentas DEMO se crean solas (`Demo:SyntheticEmployees`, `Authentication:Mode=LocalDemo`).
- Sin `Authentication__Jwt__SigningKey`, la API genera una llave en memoria. Al reiniciar la API, los tokens
  anteriores dejan de valer y la app vuelve a pedir inicio de sesión (recibe un 401 y cierra la sesión).

### 2. Dirección del servidor en la app

| Destino | URL (pantalla Ajustes o enlace "Cambiar" del login) |
|---|---|
| Emulador de Android | `http://10.0.2.2:5201/` (valor por defecto en Android) |
| Simulador de iOS (en la misma Mac) | `http://localhost:5201/` (valor por defecto en iOS) |
| Android físico por USB | ejecuta `adb reverse tcp:5201 tcp:5201` y usa `http://localhost:5201/` |
| Servidor real | `https://…` (**obligatorio HTTPS**) |

La URL se guarda con `Preferences`. Si cambias de servidor con una sesión abierta, la app cierra la sesión.

HTTP sin cifrar se permite **solo** hacia `10.0.2.2` y `localhost`, únicamente para DEMO. Esto aplica en tres
lugares: `Platforms/Android/Resources/xml/network_security_config.xml`, `NSAppTransportSecurity` en `Info.plist`
(solo `localhost`) y la validación de `ServerSettings`.

### 3. Ejecutar la app

```bash
# Android (con un emulador encendido o un dispositivo conectado)
dotnet build src/GPV.ProductTimeFlow.Mobile -t:Run -f net10.0-android

# iOS (en macOS)
dotnet build src/GPV.ProductTimeFlow.Mobile -t:Run -f net10.0-ios
```

También puedes abrir la carpeta en Visual Studio o VS Code y elegir el destino (emulador o simulador).

Cuentas sintéticas de DEMO (contraseña `Demo#TimeFlow2026`). El login las muestra solo si el último servidor
informó modo `Demo`, o si todavía no se conoce el modo:

- `ana.empleada@demo.timeflow.example`: empleada
- `laura.jefa@demo.timeflow.example`: jefa directa (filtro 1)
- `carlos.superior@demo.timeflow.example`: jefe superior (filtro 2)
- `registro.admin@demo.timeflow.example`: registro administrativo (filtro 3)
- `admin.producto@demo.timeflow.example`: administración de Producto

---

## Generar un APK firmado (Android, distribución interna)

En Release, el proyecto genera un **APK** (`AndroidPackageFormat=apk`), no un AAB.

### 1. Crear el keystore (una sola vez)

```bash
keytool -genkeypair -v \
  -keystore gpv-timeflow.keystore \
  -alias gpvtimeflow \
  -keyalg RSA -keysize 2048 -validity 10000
```

- Guarda el keystore **fuera del repositorio**, en una bóveda o un secreto de CI.
  **Nunca lo subas al repositorio.** El `.gitignore` de esta carpeta ignora `*.keystore`, `*.jks`, `*.p12` y otros.
- Si pierdes el keystore, no podrás publicar actualizaciones sobre las instalaciones existentes.

### 2. Publicar

```bash
export TF_KEYSTORE_PASS='…'   # o configúralas como secretos de CI
export TF_KEY_PASS='…'

dotnet publish src/GPV.ProductTimeFlow.Mobile -f net10.0-android -c Release \
  -p:AndroidKeyStore=true \
  -p:AndroidSigningKeyStore=/ruta/segura/gpv-timeflow.keystore \
  -p:AndroidSigningKeyAlias=gpvtimeflow \
  -p:AndroidSigningStorePass=env:TF_KEYSTORE_PASS \
  -p:AndroidSigningKeyPass=env:TF_KEY_PASS
```

El APK firmado queda en
`src/GPV.ProductTimeFlow.Mobile/bin/Release/net10.0-android/publish/com.gpvamericas.producttimeflow-Signed.apk`.
Para instalarlo en un dispositivo: `adb install -r <archivo>.apk`.

> Con el prefijo `env:`, las contraseñas no quedan en el historial del shell ni en los logs de MSBuild.

---

## Compilar y firmar para iOS (macOS + Xcode)

1. Instala Xcode y ábrelo una vez para aceptar la licencia. Ejecuta `xcode-select -s /Applications/Xcode.app`.
2. En el portal de Apple Developer:
   - Crea el **App ID** `com.gpvamericas.producttimeflow`.
   - Crea un certificado **Apple Distribution** (o *Apple Development* para pruebas) e instálalo en el llavero
     de la Mac.
   - Crea un **perfil de aprovisionamiento** (Ad Hoc, In-House/Enterprise o App Store) para ese App ID y
     descárgalo (doble clic para instalarlo).
3. Publica:

```bash
dotnet publish src/GPV.ProductTimeFlow.Mobile -f net10.0-ios -c Release \
  -p:ArchiveOnBuild=true \
  -p:RuntimeIdentifier=ios-arm64 \
  -p:CodesignKey="Apple Distribution: GPV Americas (TEAMID)" \
  -p:CodesignProvision="GPV TimeFlow AdHoc"
```

El `.ipa` queda en `bin/Release/net10.0-ios/ios-arm64/publish/`. Para subirlo a TestFlight usa Transporter o
`xcrun altool`. Para distribución Ad Hoc o empresarial usa tu MDM.

Notas:
- `Platforms/iOS/Entitlements.plist` declara el grupo de Keychain que necesita `SecureStorage`; es imprescindible
  en el simulador. El grupo es el predeterminado de la app, así que no requiere habilitar *Keychain Sharing*.
- `PrivacyInfo.xcprivacy` declara las APIs *required reason* que usa .NET MAUI (Preferences/NSUserDefaults,
  marcas de tiempo de archivos, etc.). Apple lo exige para publicar.
- En producción no agregues excepciones a ATS: el servidor debe usar HTTPS con un certificado válido.

---

## Funcionalidad y contrato usado

| Pantalla | Llamadas (`TimeFlowApiClient`) |
|---|---|
| Login | `LoginAsync`. El JWT se guarda en `SecureStorage`; al abrir la app, `MeAsync` revalida la sesión |
| Inicio (`Hola, {FirstName}`) | `DashboardAsync`: contadores, vacaciones disponibles, tiempo extra del mes, bandeja de aprobación (jefa directa/jefe superior) y pendientes administrativos (registro administrativo) |
| Nueva / Corregir | `LeaveCategoriesAsync`, `OvertimePreviewAsync` y `VacationPreviewAsync` (en vivo), `CreateRequestAsync`/`UpdateRequestAsync`, `UploadAttachmentAsync` (FilePicker; pdf/png/jpg/jpeg/docx/xlsx ≤ 10 MB), `SubmitAsync` con firma opcional y una clave de idempotencia **por pantalla** |
| Solicitudes | `ListRequestsAsync` con `Scope` Mine (filtros open/approved/rejected/returned/drafts), ApprovalInbox y Administrative, según `UserRole` |
| Detalle | `GetRequestAsync`. Muestra resumen, filtros (Steps), firmas (IsValid, ImageDataUrl), adjuntos, registro administrativo e historial. Acciones según `Permissions`: `SubmitAsync`, `CancelAsync`, `DecideAsync` (aprobar exige firma dibujada y la casilla de consentimiento; rechazar o devolver exige comentario de ≥ 10 caracteres; se envían `ExpectedVersion` y una clave por diálogo) y `AdministrativeAsync` (Receive/Observe/Register/Complete). `DownloadPdfAsync` y `DownloadAttachmentAsync` guardan el archivo en `FileSystem.CacheDirectory` y lo abren con `Launcher.OpenAsync(OpenFileRequest)` |
| Calendario | `CalendarAsync` (Mine/Team). Cuadrícula mensual con colores por tono (overtime, vacation, paidleave, unpaidleave, peer, holiday) |
| Vacaciones | `VacationBalanceAsync`: asignados, usados, aprobados por disfrutar, en trámite, disponibles y movimientos |
| Notificaciones | `NotificationsAsync`, `MarkNotificationReadAsync`, `UnreadCountAsync` (cada 60 s) y SignalR `/hubs/notifications` (evento `notification`, token vía `AccessTokenProvider`) para la insignia y los avisos |
| Ajustes | URL del servidor, estado del tiempo real, ambiente, versión y cierre de sesión |

Diseño: tarjetas y chips con los tonos de `Labels.StatusTone` (neutral, warning, info, attention, danger, success,
muted). Los tipos, estados y filtros siempre se muestran con `Labels`, nunca con nombres de enum. El tema claro u
oscuro sigue `prefers-color-scheme`, la navegación inferior tiene cinco pestañas (Inicio, Solicitudes, Nueva,
Calendario, Más) y el diseño está pensado para pantallas desde 360 px de ancho (no se probó en un dispositivo).

### Lo que la app NO hace (por diseño o pendiente)

- **No calcula ni aplica descuentos de nómina.** Los permisos sin goce muestran un aviso explícito.
- **No hay notificaciones push** (FCM o APNs). El tiempo real solo funciona con la app en primer plano (SignalR),
  con un respaldo de sondeo cada 60 s.
- **No funciona con `Authentication:Mode=EntraId`.** En ese modo la API no expone `/api/v1/auth/login` y la app aún
  no tiene un flujo MSAL. Solo funciona con la API en modo LocalDemo o Test.
- El cierre de sesión solo ocurre en el dispositivo (borra el token de `SecureStorage`), porque la API no tiene un
  endpoint para revocar tokens.
- No hay modo sin conexión. Si la API no responde al abrir la app, se usa el perfil guardado y las pantallas
  muestran "No se pudo conectar con el servidor".
- Si el ancho del panel de firma cambia (por ejemplo, al rotar el dispositivo), el panel se borra y hay que firmar
  de nuevo.

---

## Estado de verificación

**El proyecto MAUI no se compiló ni se ejecutó.** En el entorno de entrega:

| Verificación | Resultado |
|---|---|
| `dotnet build GPV.ProductTimeFlow.sln` (raíz) | ✅ Sigue compilando; el proyecto móvil no está en la solución |
| `dotnet build` del `.csproj` móvil | ⛔ `NETSDK1147: … workloads must be installed: maui-android` (esperado). Confirma que el multi-target se evalúa (`net10.0-android`) |
| Componentes Razor y servicios C# | ✅ Se compilaron sin errores ni advertencias en un proyecto temporal `net10.0` fuera del repositorio, contra `GPV.ProductTimeFlow.Shared` real y con *stubs* que imitan las firmas de MAUI Essentials (`Preferences`, `SecureStorage`, `FileSystem`, `FilePicker`, `Launcher`, `DeviceInfo`, `AppInfo`, `MainThread`). Esto valida los DTOs, los nombres de parámetros de los componentes y los `using`, pero **no** valida XAML, plataformas ni empaquetado |
| XML (csproj, XAML, manifest, plist, SVG) y `signature.js` | ✅ Sintaxis válida (`xml.dom.minidom` y `node --check`) |

### Pasos pendientes en una máquina con MAUI

1. `dotnet workload install maui-android maui-ios` y `dotnet restore src/GPV.ProductTimeFlow.Mobile`.
2. `dotnet build src/GPV.ProductTimeFlow.Mobile -f net10.0-android`. Corregir cualquier error de XAML, de
   recursos o de ambigüedad con los `global using` implícitos de MAUI.
3. Ejecutar en el emulador de Android contra la API (`--launch-profile http`) y probar el flujo completo con las
   cinco cuentas DEMO:
   - Crear borradores de los cuatro tipos y revisar las vistas previas (incluido el cruce de medianoche y los
     días hábiles).
   - Adjuntar un PDF y una imagen, y probar el rechazo de un archivo de más de 10 MB.
   - Enviar con y sin firma, y comprobar que un doble toque no duplica el envío.
   - Aprobar con firma, rechazar o devolver con comentario, y provocar un conflicto de versión.
   - Probar las acciones administrativas.
   - Descargar el PDF y confirmar que se abre en el visor del sistema.
   - Comprobar el calendario, las vacaciones y las notificaciones (la insignia en tiempo real con otra sesión
     aprobando).
   - Reiniciar la API y confirmar que la app cierra la sesión por 401.
4. Comprobar la CSP de `wwwroot/index.html` con BlazorWebView. Si la app queda en blanco, revisar la consola
   (`AddBlazorWebViewDeveloperTools` está activo en Debug: `chrome://inspect` en Android y Safari › Desarrollo
   en iOS).
5. Verificar la política de red: HTTP hacia una IP de la LAN debe fallar y `10.0.2.2` debe funcionar.
6. Verificar `SecureStorage` en el simulador de iOS (con el entitlement de Keychain) y en un dispositivo.
7. Generar el APK firmado y el IPA con los comandos de arriba e instalarlos en dispositivos físicos.
8. Revisar la accesibilidad (TalkBack/VoiceOver) y los tamaños de fuente grandes.
9. En Release, confirmar que el recorte (trimming) no rompe la deserialización. El cliente compartido usa
   System.Text.Json por reflexión; con el `TrimMode` por defecto de MAUI (`partial`) los ensamblados de la app no se
   recortan. Si se activa `TrimMode=full`, hay que agregar un `JsonSerializerContext` en Shared.

---

## Huecos del contrato API detectados (no se modificó la API)

1. `TimeFlowApiClient` no expone `POST /api/v1/notifications/read-all` ni
   `DELETE /api/v1/requests/{id}/attachments/{attachmentId}`, aunque los endpoints existen.
   `Services/TimeFlowApiClientExtensions.cs` los implementa temporalmente con el mismo `HttpClient`.
2. El cliente compartido reemplaza el `detail` de **cualquier 401** por "Tu sesión expiró…". En el login, la app
   no puede mostrar el motivo real (credenciales inválidas, cuenta inactiva…) y muestra "Correo o contraseña
   incorrectos". El 423 (cuenta bloqueada) sí conserva el mensaje del servidor.
3. No hay un endpoint anónimo que informe el modo del ambiente (Demo o Production) antes del login. `/health` no lo
   incluye. Por eso el aviso de cuentas DEMO se basa en el último modo que el servidor reportó al iniciar sesión.
4. No hay refresh token ni endpoint para revocar la sesión. Al vencer el JWT (480 min) hay que volver a iniciar
   sesión.
5. No hay login móvil en modo Entra ID (se necesitaría MSAL y un *app registration* público para la app).
6. La política `RequireEmployeeSignature` solo la puede leer Administración de Producto
   (`GET /admin/settings/policy`). La app no sabe de antemano si la firma del solicitante es obligatoria y solo
   muestra el error del servidor al enviar.
7. Las extensiones permitidas y el tamaño máximo de los adjuntos no se exponen por la API. Se copiaron de
   `WorkflowService` (`DeviceFiles.AllowedTypes` y `MaxAttachmentBytes`) y hay que mantenerlos sincronizados.
8. `NotificationDto.Link` apunta a rutas de la app web. La app móvil navega con `RequestId`.
9. El hub de SignalR usa el serializador por defecto (enums numéricos) y REST usa enums como texto. El cliente móvil
   acepta ambos (`JsonStringEnumConverter`), pero conviene unificarlos.
10. El perfil `https` de `launchSettings.json` más `UseHttpsRedirection` dificultan las pruebas con el emulador.
    Kestrel escucha solo en `localhost`, así que un dispositivo físico necesita `adb reverse` o HTTPS publicado.
11. No hay endpoint para eliminar un borrador (solo cancelar) ni para registrar dispositivos para push.
