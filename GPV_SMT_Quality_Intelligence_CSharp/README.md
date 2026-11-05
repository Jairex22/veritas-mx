# GPV SMT Quality Intelligence — versión C# (.NET 10)

**GPV Americas E-MXG** · Trazabilidad de unidades, actividad SMT, defectos y detección de reprocesos sobre **FactoryLogix OData** (`SMT`, `Quality`, `QualityHistory`).

Reconstrucción completa en C# de la versión Python (`../GPV_SMT_Quality_Intelligence`). Misma interfaz web, mismos módulos, mismas reglas y el mismo contrato JSON: ambas versiones se compararon endpoint por endpoint con resultados equivalentes (ver `docs/TEST_EVIDENCE.md`).

> ⚠️ **Estado:** lista para piloto en **modo demostración**. Se compiló y probó en Linux con salida para Windows x64; **todavía no se ha ejecutado en un equipo Windows real** ni contra FactoryLogix real. Ver `docs/LIMITATIONS.md`.

---

## 1. Ejecutar (sin instalar nada)

Descomprima `GPV_SMT_Quality_Intelligence_win-x64.zip` en una carpeta, por ejemplo `C:\GPV\SQI\`. Contiene:

```
GPV.SMT.QualityIntelligence.exe   (incluye .NET; no requiere instalación ni permisos de administrador)
config.example.json
wwwroot\   (interfaz web)
fixtures\  (datos de demostración)
```

En **PowerShell**:

```powershell
cd C:\GPV\SQI
.\GPV.SMT.QualityIntelligence.exe
```

En **cmd**: `GPV.SMT.QualityIntelligence.exe`

Se abre `http://127.0.0.1:8765/`. No cierre la ventana de consola mientras use la app; `Ctrl + C` la detiene.

| Opción | Uso |
|---|---|
| `--no-browser` | No abre el navegador |
| `--port 8800` | Otro puerto (si 8765 está ocupado) |
| `--check` | Muestra modo, URL, banderas de seguridad y qué `config.json` se leyó, y sale |
| `--set-credential` | Guarda usuario/contraseña en el Administrador de credenciales de Windows |

**Si Windows muestra "Windows protegió su PC" (SmartScreen):** el `.exe` no está firmado digitalmente. Pulse *Más información → Ejecutar de todas formas*, o pida a TI que lo autorice. Si AppLocker bloquea el `.exe`, siga usando la versión Python.

## 2. Modo demostración

Arranca en **DEMO** por defecto (barra naranja). Identificadores de prueba: `W07632100028` (caso Mirion), `DEMO-00009`, `DEMO-00018`, `DEMO-QH-FAIL`, `DEMO-ERR-401`, `DEMO-ERR-403`, `DEMO-ERR-500`, `DEMO-TIMEOUT`, `DEMO-INVALID-JSON`, `NOEXISTE123`. Batches: `W076321`, `DEMO-B100`, `DEMO-B200`, `DEMO-B300`.

## 3. Conexión real (requiere aprobación de TI/MES)

`config.json` debe estar **en la misma carpeta del `.exe`** (o en la carpeta desde donde lo ejecuta).

```powershell
Copy-Item config.example.json config.json
notepad config.json
```

Cambie `"mode": "live"`, `"live_mode_approved": true` y, si FactoryLogix pide usuario, `"auth_method": "basic"`, `"credential_source": "windows_credential_manager"` y `"allow_basic_auth_over_http": true` (solo con visto bueno de TI: sobre `http://` la contraseña viaja sin cifrar). **Nunca** escriba contraseñas en `config.json`; la app se niega a iniciar si encuentra una.

```powershell
.\GPV.SMT.QualityIntelligence.exe --set-credential
.\GPV.SMT.QualityIntelligence.exe --check
.\GPV.SMT.QualityIntelligence.exe
```

Luego en la app: **Diagnóstico OData → Probar $metadata → Probar SMT**.

Novedad respecto a Python: `odata.connect_timeout_seconds` (por defecto 5 s) separa el tiempo de conexión del tiempo total (`timeout_seconds`, 10 s).

### Protección de FactoryLogix (v1.1.0)

| Medida | Valor por defecto | Efecto |
|---|---|---|
| Sin consultas automáticas | — | Pulse y Quality solo consultan al pulsar el botón |
| `$select` (`odata.use_select`) | activado | Solo se piden las columnas que la app usa (Quality: ~22 de ~47) |
| Sin `$orderby` en búsquedas | — | El orden se hace en la app; FactoryLogix no ordena |
| `odata.max_retries` | 0 | Un HTTP 500 lento no se repite |
| `odata.max_pages` | 1 | No se siguen páginas adicionales |
| `protection.cooldown_seconds` | 60 | Tras timeout / 5xx / 429 / error de red, esa entidad no se consulta durante 60 s (estado `COOLDOWN`, nunca se interpreta como "sin registros") |
| `protection.result_cache_seconds` | 60 | La misma consulta dentro de 60 s se responde desde memoria |
| `protection.min_interval_ms` | 1000 | Separación mínima entre solicitudes |
| Límites | Pulse 200, Quality 200 (4 h), trazabilidad 100/50/200, rework 500 | Menos filas por consulta |
| `odata.metadata_ttl_minutes` | 1440 | `$metadata` se descarga una vez al día |

Los valores de un `config.json` existente tienen prioridad: actualícelo con `config.example.json`.

## 4. Compilar desde código (equipo con .NET 10 SDK)

```powershell
dotnet test
dotnet run --project src/Gpv.Sqi
dotnet publish src/Gpv.Sqi/Gpv.Sqi.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o publish
```

Dependencias NuGet: `Microsoft.Data.Sqlite` 10.0.14 y `SQLitePCLRaw.lib.e_sqlite3` 2.1.14 (fijada para corregir el aviso de seguridad GHSA-2m69-gcr7-jv3q de la versión anterior). Pruebas: xUnit.

## 5. Estructura

```
GPV_SMT_Quality_Intelligence_CSharp/
├── Gpv.Sqi.slnx
├── src/Gpv.Sqi/
│   ├── Program.cs                 Punto de entrada y opciones de línea de comandos
│   ├── Api/                       Servidor Kestrel (Host/CSRF/CSP), handlers, validación de entradas
│   ├── Config/                    Configuración y credenciales (env / Credential Manager vía P/Invoke)
│   ├── OData/                     Cliente FactoryLogix, filtros seguros, $metadata, parser JSON
│   ├── Demo/                      Fuente de demostración + inyección de fallos
│   ├── Data/                      SQLite: esquema, caché, auditoría, ajustes
│   ├── Analytics/                 Defectos únicos, línea de tiempo, reglas R01–R09, evidencia
│   ├── Services/                  Trazabilidad, Pulse, Quality, Rework, ventanas de tiempo
│   ├── Reports/                   CSV, XLSX (OOXML nativo) y HTML imprimible
│   ├── Infrastructure/            JSON, logs sanitizados, fechas OData
│   ├── wwwroot/                   Interfaz web (idéntica a la versión Python)
│   └── fixtures/                  Caso Mirion + $metadata de muestra
├── tests/Gpv.Sqi.Tests/           125 pruebas xUnit (sin red real)
└── docs/
```
