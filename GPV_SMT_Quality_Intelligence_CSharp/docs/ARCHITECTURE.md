# Arquitectura (C#)

Port 1:1 de la versión Python. Las reglas de negocio, estados y textos son los mismos; el frontend se sirve sin cambios (solo la etiqueta "Python" del diagnóstico pasó a "Runtime").

| Python | C# |
|---|---|
| `http.server` + `backend/server.py` | Kestrel (`WebApplication.CreateSlimBuilder`) en `Api/WebServer.cs` |
| `backend/api.py` | `Api/ApiHandlers.cs` |
| `backend/config.py` | `Config/AppConfig.cs` (configuración como `JsonObject`, rutas con punto) |
| `backend/credentials.py` (ctypes) | `Config/Credentials.cs` (P/Invoke `CredReadW`/`CredWriteW`) |
| `services/odata_client.py` (urllib) | `OData/FactoryLogixODataClient.cs` (`HttpClient` + `SocketsHttpHandler`: sin proxy, sin redirecciones, `ConnectTimeout` separado) |
| `services/odata_filters.py` | `OData/ODataFilterBuilder.cs` |
| `services/metadata.py` | `OData/MetadataParser.cs` (`DtdProcessing.Prohibit`) |
| `services/demo_source.py` | `Demo/DemoDataSource.cs` |
| `database/` + `repositories/` (sqlite3) | `Data/` (`Microsoft.Data.Sqlite`, esquema incrustado) |
| `analytics/` | `Analytics/` |
| `services/*_service.py` | `Services/` (asíncronos) |
| `reports/` (zipfile) | `Reports/` (`System.IO.Compression`) |
| `backend/logging_setup.py` | `Infrastructure/AppLog.cs` |

Flujo de consulta, seguridad, modelo de datos SQLite (mismo `schema.sql`) y reglas de deduplicación: idénticos a `../GPV_SMT_Quality_Intelligence/docs/ARCHITECTURE.md`.

Diferencias:
- Timeout de conexión (`odata.connect_timeout_seconds`) separado del timeout total.
- Concurrencia con `SemaphoreSlim` asíncrono; las consultas no bloquean hilos del servidor.
- `config.json` se busca en el directorio actual y, si no existe, junto al `.exe`; base de datos y logs se crean en esa misma carpeta.
