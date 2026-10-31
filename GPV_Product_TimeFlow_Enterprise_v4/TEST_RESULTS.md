# Registro de pruebas (QA) · GPV Product TimeFlow 4.0.0

**Fecha de ejecución:** 31 de octubre de 2026
**Entorno:** contenedor Linux Ubuntu 24.04.5, 4 vCPU, 15 GB RAM. .NET SDK 10.0.114 (runtime 10.0.14), SQLite, Chromium de Playwright (build 1243). Sin acceso a Microsoft 365, SQL Server, Android SDK ni Xcode.

Ningún resultado se infirió: todo lo que dice «Aprobado» se ejecutó en este entorno. Lo no ejecutado se marca como **Pendiente**.

## 1. Compilación

| Prueba | Resultado | Evidencia |
|---|---|---|
| `dotnet restore` de la solución (Web, API, Application, Domain, Infrastructure, Shared y 4 proyectos de prueba) | Aprobado | Restauración desde cero tras borrar `bin/` y `obj/` |
| `dotnet build GPV.ProductTimeFlow.sln` | **Aprobado: 0 errores, 0 advertencias** | Salida de MSBuild (12.5 s) |
| Migraciones EF Core SQLite y SQL Server | Aprobado (generadas); SQLite aplicada en cada arranque | `Infrastructure/Persistence/Migrations/*`, `deployment/sql/sqlserver-idempotent.sql` |
| Proyecto Mobile (.NET MAUI, `net10.0-android`) | **Pendiente: no compilado** | `NETSDK1147`: el workload MAUI no puede instalarse en el SDK de Ubuntu. El código Razor/C# se compiló en un proyecto auxiliar con stubs de las APIs MAUI: 0 errores. XAML, código de plataforma y empaquetado sin verificar |

## 2. Pruebas automatizadas

| Suite | Total | Aprobadas | Fallidas | Omitidas | Duración |
|---|---:|---:|---:|---:|---|
| Unitarias (`tests/UnitTests`) | 150 | 150 | 0 | 0 | 11 s |
| Integración (`tests/IntegrationTests`, API real sobre SQLite temporal) | 26 | 26 | 0 | 0 | 11 s |
| End-to-end (`tests/EndToEndTests`, Playwright + Chromium + Web real en Kestrel) | 11 | 11 | 0 | 0 | 1 min 13 s |
| **Total** | **187** | **187** | **0** | **0** | |

Los resultados fueron estables en ejecuciones repetidas, incluida una ejecución completa desde cero.

### 2.1 Unitarias (150)
- **Tiempo extra:** cálculo normal, cruce de medianoche (22:00→01:30 = 3.5 h), redondeo y validación de horas iguales.
- **Vacaciones y calendario:** días hábiles con fines de semana y festivos configurados; tabla de antigüedad (1→12, 5→20, 6→22, 11→24).
- **Folios:** formato y validación.
- **Máquina de estados:** las 20 transiciones válidas, transiciones inválidas, estados terminales e imposibilidad de saltar el filtro 1.
- **Hashes:** de contenido (cambia con motivo, fechas o adjuntos), de firma y cadena de auditoría.
- **Excel:** inyección de fórmulas neutralizada (`=HYPERLINK(...)` queda como texto) y estructura (Resumen, Detalle, Metadatos, encabezado fijo, autofiltro).
- **PDF:** generación válida (`%PDF`) con firmas y QR. PNG de firma sintética.
- **Reglas sobre SQLite real:**
  - duplicados y traslapes rechazados;
  - saldo insuficiente;
  - el permiso sin goce exige justificación y clasificación;
  - nadie autoriza lo propio;
  - aprobar exige firma y consentimiento; rechazar exige comentario de 10 caracteres o más;
  - una versión desactualizada genera conflicto;
  - el reenvío invalida las firmas previas;
  - el descuento de vacaciones ocurre exactamente una vez;
  - folios únicos y consecutivos;
  - la verificación de auditoría pasa con datos íntegros y **detecta la alteración** de un registro hecha con SQL directo.

### 2.2 Integración (26)
| Prueba | Resultado |
|---|---|
| Login válido / 401 genérico (usuario inexistente = contraseña errónea) / bloqueo 423 tras 5 fallos / 10 logins paralelos misma cuenta | Aprobado |
| Peticiones sin autenticación → 401; cliente tipado `TimeFlowApiClient` | Aprobado |
| Flujo completo por HTTP: crear → enviar → jefa firma/aprueba → jefe firma/aprueba → registro: recibir, registrar, procesar → Completada; Excel exportado y registrado en `ExcelExports`; correos de todos los eventos en la cola; procesamiento Mock → `MockDelivered` (no `Sent`) y HTML en `mail-drop` | Aprobado |
| PDF del expediente completado (`application/pdf`, `%PDF`) | Aprobado |
| Rechazo de jefa (el jefe ya no puede decidir), rechazo del jefe es final, devolución → edición → reenvío con nueva versión y firmas invalidadas, cancelación | Aprobado |
| Vacaciones: el saldo se descuenta una sola vez | Aprobado |
| **IDOR**: empleado ajeno → 404 al leer, editar, enviar o cancelar; jefa no ve borradores; registro no ve antes de la aprobación final; empleado en endpoints de administración → 403; ID de adjunto manipulado → 404 | Aprobado |
| Adjuntos: PDF válido aceptado; PDF falso (magic bytes) → 422; `.exe` → 422 | Aprobado |
| Verificación pública QR sin datos personales; código erróneo → 404; cabeceras de seguridad presentes | Aprobado |
| **Concurrencia**: 2 aprobaciones simultáneas → exactamente 1 éxito y 1 conflicto 409, una sola decisión en BD; misma clave de idempotencia → `WasDuplicate`; 10 envíos paralelos → 1 éxito; borradores paralelos → folios únicos | Aprobado |

### 2.3 End-to-end con navegador (11)
| Escenario | Resultado |
|---|---|
| **Flujo de 13 pasos**: Ana inicia sesión («Hola, Ana») → asistente de tiempo extra con cruce de medianoche (3.5 h) → envía → Laura firma en el lienzo y aprueba → Carlos firma y aprueba → Sofía lo ve en registro → descarga Excel (folio presente en *Detalle*) y PDF (`%PDF`) → recibe, registra y procesa → Ana ve «Completada» con 2 firmas vigentes | Aprobado |
| Rechazo por jefa; devolución, corrección y reenvío; cancelación por empleado; registro sin acceso antes de la autorización final | Aprobado |
| Visual en 1920×1080, 1366×768, 768×1024, 390×844 y 360×800 (inicio, nueva solicitud, calendario, aprobaciones): **sin desbordamiento horizontal**, capturas guardadas | Aprobado |
| Login, tema oscuro, gestión de empleados y verificación de la auditoría desde la UI («Cadena íntegra») | Aprobado |

Evidencia: 30 capturas reales en `docs/screenshots/` y el PDF de ejemplo `docs/screenshots/ejemplo-expediente.pdf`, generados por estas pruebas. No aparecieron errores en la consola del navegador (verificado con un script de Playwright tras corregir la CSP).

## 3. Prueba de carga (200 usuarios virtuales)

**Comando:** `scripts/load-test.sh`, es decir `tests/LoadTests` contra la API en Release sobre SQLite.

**Datos:** 200 empleados sintéticos. Cada usuario virtual inicia sesión con una cuenta distinta y ejecuta durante 90 s una mezcla de tablero, listados, notificaciones, calendario, saldo, vista previa y creación de borradores, con pausas de 0.5 a 2 s. Después, 2 aprobaciones simultáneas por cada solicitud de la bandeja.

| Operación | Solicitudes | p50 | p95 | p99 |
|---|---:|---:|---:|---:|
| GET /dashboard | 3 662 | 7 ms | 15 ms | 527 ms |
| GET /requests | 2 826 | 4 ms | 10 ms | 527 ms |
| GET /calendar | 1 714 | 5 ms | 11 ms | 527 ms |
| GET /vacations/balance | 1 791 | 4 ms | 9 ms | 527 ms |
| POST /requests (borrador, escritura) | 897 | 9 ms | 20 ms | 527 ms |
| POST /decision (aprobación) | 14 | 67 ms | 126 ms | 126 ms |
| POST /auth/login (200 simultáneos) | 200 | 5 416 ms | 5 451 ms | 5 569 ms |
| **Total** | **14 638** | 5 ms | 15 ms | 2 775 ms |

- **Throughput:** 160 solicitudes por segundo en la fase mixta.
- **Errores** (5xx, 429, timeouts): **0 (0.00 %)**.
- **Dobles aprobaciones:** **0**.
- **Recursos de la API:** CPU promedio 20 % (máximo 47 %) de 4 núcleos; RAM máxima 285 MB.

**Interpretación:**
- **Objetivos cumplidos en este entorno:** p95 menor de 2 s en consultas comunes, menos de 1 % de errores y ninguna doble aprobación.
- **Picos de p99 (~527 ms):** coinciden con escrituras simultáneas sobre SQLite.
- **Login:** el p95 de ~5.4 s se debe a 200 inicios de sesión **simultáneos** con PBKDF2 de 100 000 iteraciones, que satura la CPU de forma deliberada como defensa contra fuerza bruta. En producción el inicio de sesión lo realiza Entra ID.
- **Alcance:** esto **no certifica** la capacidad en producción. Debe repetirse en infraestructura representativa con SQL Server (scripts incluidos, incluido k6).
- **Evidencia:** `docs/evidencias/load-result-202610311526.md`.

**k6:** el script `tests/LoadTests/k6/timeflow-load.js` está entregado pero **no se ejecutó**, porque k6 no está disponible en el entorno.

## 3.1 Verificación del ZIP

| Paso | Resultado |
|---|---|
| `scripts/package-zip.sh` → `GPV_Product_TimeFlow_Enterprise_v4.0.0.zip` (343 archivos, 5.6 MB) sin `bin/`, `obj/`, bases de datos, `App_Data` ni secretos | Aprobado |
| Extracción en carpeta temporal y búsqueda de secretos o bases de datos | Aprobado (ninguno) |
| `dotnet restore` + `dotnet build` desde la carpeta extraída | Aprobado (0 errores, 0 advertencias) |
| `dotnet test` unitarias (150) e integración (26) desde la carpeta extraída | Aprobado |

## 4. Errores encontrados y corregidos durante QA

| Hallazgo | Corrección |
|---|---|
| PDFsharp-MigraDoc 6.5.0 cambió a licencia AGPL y exige registrar licencia, por lo que el PDF fallaba con 500 | Se cambió a 6.2.4 (MIT). Prueba de PDF reactivada y aprobada |
| Inicios de sesión simultáneos de la misma cuenta daban 500 por concurrencia en `LastLoginUtc` | Contabilidad de login con `ExecuteUpdate` atómico, sin token de concurrencia. Prueba reactivada y aprobada |
| El reenvío tras editar incrementaba la versión dos veces | Solo se incrementa si no hubo edición previa |
| Entidades nuevas con clave Guid se marcaban como modificadas | Claves Guid declaradas como asignadas por la aplicación |
| Colisión de clave en la auditoría encadenada | Columna `Sequence` única para la cadena |
| Arranque DEMO tardaba 4 min (fsync por commit en SQLite) | `PRAGMA synchronous=NORMAL` con WAL. Ahora tarda unos 20 s |
| Binding de consulta en la API exigía `page` | Parámetros opcionales explícitos |
| CSP bloqueaba el *import map* en línea | Se retiró el *import map* (no se usa) |
| Cookies `__Host-` impedían HTTP local en desarrollo/E2E | Política estricta fuera de Development y `SameAsRequest` en Development |

## 5. Pruebas pendientes (no ejecutadas)

- Envío real con Microsoft Graph e inicio de sesión con Microsoft Entra ID, que requieren tenant y autorización de TI.
- SQL Server: script generado, pero sin ejecutar contra una instancia.
- Compilación, APK y pruebas de la app MAUI en Android y en iOS.
- Navegadores Safari, Firefox y Edge, y dispositivos iPhone y Android reales. Solo se automatizó Chromium.
- Auditoría formal de accesibilidad WCAG 2.2 AA con lector de pantalla.
- Carga en infraestructura representativa con SQL Server, y k6.
- Pruebas de penetración independientes.
