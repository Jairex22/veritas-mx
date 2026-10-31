# Manual de instalación · GPV Product TimeFlow 4.0.0

## 1. Requisitos

| Componente | Versión | Necesario para |
|---|---|---|
| .NET SDK | 10.0.100 o superior (`global.json` permite feature bands posteriores) | Todo |
| Visual Studio Code + **C# Dev Kit** | Actual | Edición y depuración (recomendado) |
| Navegador | Edge, Chrome, Firefox o Safari actuales | Uso de la web |
| PowerShell 7 (`pwsh`) | Opcional | Instalar Chromium para pruebas E2E |
| SQL Server | 2019+ / Azure SQL | Solo producción |
| Workload MAUI + Android SDK 35 + JDK 17 | Opcional | App móvil (ver `src/GPV.ProductTimeFlow.Mobile/README.md`) |

Compruebe: `dotnet --list-sdks` debe mostrar `10.0.x`.

## 2. Abrir en Visual Studio Code

1. `Archivo → Abrir carpeta…` → `GPV_Product_TimeFlow_Enterprise_v4`.
2. Acepte instalar las extensiones recomendadas (`.vscode/extensions.json`).
3. **Ejecutar y depurar** (Ctrl+Shift+D) → elija:
   - `Web (DEMO) · https://localhost:7101`
   - `API (DEMO) · http://localhost:5201`
   - `Web + API (DEMO)` (ambas)
4. Tareas (Ctrl+Shift+P → *Run Task*): `build`, `test (unit + integración)`, `test e2e (Playwright)`, `run web (DEMO)`, `run api (DEMO)`.

## 3. Comandos exactos (terminal en la raíz)

```bash
dotnet restore
dotnet build
dotnet test tests/UnitTests
dotnet test tests/IntegrationTests
dotnet run --project src/GPV.ProductTimeFlow.Web --launch-profile https
```

- Certificado HTTPS de desarrollo (una vez): `dotnet dev-certs https --trust`.
- Web: **https://localhost:7101** (perfil `http`: http://localhost:5101).
- `dotnet test` en la raíz ejecuta también las pruebas E2E, que requieren Chromium (ver §6).

### API separada (para la app móvil o integraciones)

```bash
dotnet run --project src/GPV.ProductTimeFlow.API --launch-profile http
```

- URL: **http://localhost:5201** · OpenAPI: `http://localhost:5201/openapi/v1.json` (solo DEMO/TEST).
- Web y API comparten la carpeta de datos `App_Data/` de la raíz (`TimeFlow:DataRoot = ../../App_Data`), por lo que ven las mismas solicitudes.
- En el emulador Android la app usa `http://10.0.2.2:5201/` (configurable en *Más → Configuración*).
- La Web procesa la cola de correo (`Email:ProcessorEnabled=true`); la API no (`false`) para evitar envíos duplicados. Si solo ejecuta la API, active el procesador en ella.

### Reiniciar los datos DEMO

Detenga la aplicación y borre `App_Data/` (o `./scripts/run-demo.sh --reset`, `.\scripts\run-demo.ps1 -Reset`).

## 4. Ambientes (separación DEMO / TEST / PRODUCTION)

| | DEMO | TEST | PRODUCTION |
|---|---|---|---|
| `TimeFlow:Mode` | `Demo` | `Test` | `Production` |
| Datos | 200 empleados y solicitudes sintéticos | Base vacía (solo catálogos) | Reales, cargados por Producto |
| Autenticación | Cuentas locales DEMO (PBKDF2) | Cuentas locales | **Microsoft Entra ID** obligatorio |
| Correo | Mock (no envía; HTML en `App_Data/mail-drop`) | Mock | **Microsoft Graph** obligatorio |
| Base de datos | SQLite | SQLite o SQL Server | **SQL Server** obligatorio |
| Indicador visual | Franja «AMBIENTE DEMO» y asunto `[DEMO]` | Franja «PRUEBAS» | Sin franja |

`appsettings.Test.json` y `appsettings.Production.json` contienen la configuración base; los secretos **nunca** van en archivos: use variables de entorno (`deployment/env.production.example`) o un almacén seguro. Al arrancar en `Production`, `InfrastructureRegistration.ValidateEnvironment` aborta si encuentra SQLite, Mock, cuentas locales o una URL pública sin HTTPS.

## 5. Configuración relevante

| Clave | Por defecto | Descripción |
|---|---|---|
| `TimeFlow:DataRoot` | `../../App_Data` | Base SQLite, adjuntos, buzón DEMO, llaves de protección de datos y logs |
| `TimeFlow:PublicBaseUrl` | `https://localhost:7101` | Enlaces en correos y QR de verificación |
| `TimeFlow:TimeZoneId` | `America/Mexico_City` | Zona horaria corporativa |
| `Database:Provider` / `ConnectionString` | `Sqlite` / automática | `SqlServer` en producción |
| `Authentication:Mode` | `LocalDemo` | `EntraId` en producción (+ sección `AzureAd`) |
| `Email:Provider` | `Mock` | `Graph` en producción (ver docs/CONFIGURACION_OUTLOOK.md) |
| `Demo:SyntheticEmployees` | 200 | Tamaño del sembrado DEMO |
| `RateLimiting:LoginPermitsPerMinute` (API) | 10 | Intentos de login por IP por minuto |

## 6. Pruebas end-to-end (Playwright)

```bash
dotnet build tests/EndToEndTests
pwsh tests/EndToEndTests/bin/Debug/net10.0/playwright.ps1 install chromium   # una vez
dotnet test tests/EndToEndTests
```

Las pruebas levantan la Web real en un puerto libre con una base temporal; no requieren que la aplicación esté corriendo. Las capturas se guardan en `docs/screenshots/`. Alternativas: variable `PLAYWRIGHT_BROWSERS_PATH` (navegadores ya instalados) o `TIMEFLOW_CHROMIUM_PATH` (ejecutable de Chromium).

## 7. Prueba de carga

```bash
./scripts/load-test.sh            # 200 usuarios virtuales, 120 s, API en Release
```

o con k6: `k6 run -e BASE_URL=http://localhost:5201 -e VUS=200 tests/LoadTests/k6/timeflow-load.js`.

## 8. Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| `NETSDK1045` | SDK anterior a .NET 10. Instale .NET 10. |
| El navegador advierte del certificado | Ejecute `dotnet dev-certs https --trust`. |
| No puedo iniciar sesión tras 5 intentos | Bloqueo de 15 min por fuerza bruta. El administrador puede desbloquear en *Empleados*. |
| La sesión expira tras cambiar roles | Diseño: un cambio de rol revoca las sesiones abiertas (SecurityStamp). |
| `database is locked` en SQLite con muchos procesos | Use SQL Server para cargas multiusuario reales. |
