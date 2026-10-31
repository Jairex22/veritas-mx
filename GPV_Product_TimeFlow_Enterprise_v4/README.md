# GPV Product TimeFlow Enterprise · v4.0.0

Sistema interno del **Departamento de Producto de GPV Americas** para digitalizar solicitudes de **tiempo extra, vacaciones, permisos con goce y permisos sin goce**, con flujo obligatorio de tres filtros:

```
EMPLEADO → JEFA DIRECTA (filtro 1) → JEFE SUPERIOR (filtro 2, decisión final) → REGISTRO ADMINISTRATIVO / RH (filtro 3)
```

La aplicación es propiedad funcional de **Producto**. RH participa únicamente como receptor administrativo (filtro 3); no es administrador global y no puede modificar decisiones de los jefes.

> **Estado honesto de la entrega:** la versión **Web + API** compila, se ejecutó y fue probada (unitarias, integración, end-to-end con navegador real y carga con 200 usuarios virtuales). La app **Mobile (.NET MAUI)** se entrega como proyecto completo pero **no se compiló** en el entorno de entrega (sin workload MAUI/Android SDK). Ver [TEST_RESULTS.md](TEST_RESULTS.md) y [docs/PENDIENTES_Y_DEPENDENCIAS.md](docs/PENDIENTES_Y_DEPENDENCIAS.md).

## Inicio rápido (modo DEMO, sin Microsoft 365)

Requisitos: **.NET SDK 10** (10.0.100 o superior). Nada más para la versión web.

```bash
dotnet restore
dotnet build
dotnet test tests/UnitTests
dotnet test tests/IntegrationTests
dotnet run --project src/GPV.ProductTimeFlow.Web --launch-profile https
```

Abra **https://localhost:7101**. El primer arranque crea la base SQLite en `App_Data/` y siembra 200 empleados sintéticos y ~90 solicitudes en distintos estados (≈20 s).

### Credenciales sintéticas de DEMO

| Rol | Correo | Persona sintética |
|---|---|---|
| Empleado | `ana.empleada@demo.timeflow.example` | Ana Torres Lozano |
| Jefa directa | `laura.jefa@demo.timeflow.example` | Laura Hernández Vega |
| Jefe superior | `carlos.superior@demo.timeflow.example` | Carlos Mendoza Ríos |
| Administrador de Producto | `admin.producto@demo.timeflow.example` | Miguel Ángel Ortiz Paredes |
| Registro administrativo | `registro.admin@demo.timeflow.example` | Sofía Ramírez Castro |
| Dirección (jefe superior de las jefas) | `patricia.direccion@demo.timeflow.example` | Patricia Salgado Núñez |

Contraseña común **solo DEMO**: `Demo#TimeFlow2026`. Dominio reservado `.example` (RFC 2606): no son usuarios reales. En PRODUCCIÓN las cuentas locales están deshabilitadas y se usa Microsoft Entra ID; la aplicación **se niega a arrancar** en modo `Production` si detecta autenticación DEMO, correo Mock o SQLite.

## Estructura

```
GPV_Product_TimeFlow_Enterprise_v4/
├── GPV.ProductTimeFlow.sln          Web, API, capas y pruebas (Mobile se compila aparte)
├── src/
│   ├── GPV.ProductTimeFlow.Web/            Blazor Web App (Interactive Server), PWA, SignalR, descargas
│   ├── GPV.ProductTimeFlow.API/            API REST (Minimal APIs + OpenAPI + JWT/Entra ID) para Mobile
│   ├── GPV.ProductTimeFlow.Mobile/         .NET MAUI Blazor Hybrid (Android / iOS)
│   ├── GPV.ProductTimeFlow.Application/    Casos de uso, autorización por recurso, reglas
│   ├── GPV.ProductTimeFlow.Domain/         Entidades, máquina de estados, cálculos, hashes
│   ├── GPV.ProductTimeFlow.Infrastructure/ EF Core (SQLite/SQL Server), Graph, PDF, Excel, seed
│   └── GPV.ProductTimeFlow.Shared/         Enums, DTOs, etiquetas en español, cliente HTTP tipado
├── tests/  UnitTests · IntegrationTests · EndToEndTests (Playwright) · LoadTests (+ k6/)
├── docs/   manuales, Outlook, implementación, técnica, pendientes, capturas y evidencias
├── deployment/  script SQL Server idempotente, IIS, systemd/nginx, variables de entorno de ejemplo
├── scripts/     run-demo, test-all, load-test, package-zip
├── README.md · INSTALL.md · TEST_RESULTS.md
```

Justificación de ajustes a la estructura solicitada: la Web usa los servicios de Application en proceso (sin saltos HTTP) y la API expone los mismos casos de uso para Mobile e integraciones; ambas comparten base de datos y reglas. Mobile no está en la solución raíz para que `dotnet build` funcione en equipos sin workload MAUI.

## Documentación

| Documento | Contenido |
|---|---|
| [INSTALL.md](INSTALL.md) | Requisitos y comandos exactos, VS Code, ambientes DEMO/TEST/PRODUCTION |
| [TEST_RESULTS.md](TEST_RESULTS.md) | Resultados reales de compilación y pruebas, evidencia, pendientes |
| [docs/MANUAL_USUARIO.md](docs/MANUAL_USUARIO.md) | Empleados, jefas, jefes y registro administrativo |
| [docs/MANUAL_ADMINISTRACION.md](docs/MANUAL_ADMINISTRACION.md) | Administrador de Producto |
| [docs/CONFIGURACION_OUTLOOK.md](docs/CONFIGURACION_OUTLOOK.md) | Microsoft Graph, Entra ID, permisos, secretos |
| [docs/GUIA_IMPLEMENTACION.md](docs/GUIA_IMPLEMENTACION.md) | Servidor corporativo, SQL Server, migración desde SQLite |
| [docs/DOCUMENTACION_TECNICA.md](docs/DOCUMENTACION_TECNICA.md) | Arquitectura, máquina de estados, BD, seguridad, API |
| [docs/PENDIENTES_Y_DEPENDENCIAS.md](docs/PENDIENTES_Y_DEPENDENCIAS.md) | Lo que falta y lo que depende de TI/RH |
| [src/GPV.ProductTimeFlow.Mobile/README.md](src/GPV.ProductTimeFlow.Mobile/README.md) | App móvil, APK, iOS |
| [docs/screenshots/](docs/screenshots/) | Capturas reales tomadas por las pruebas E2E |

## Licencias de terceros

ClosedXML (MIT), PDFsharp-MigraDoc 6.2.4 (MIT — se eligió deliberadamente esta versión: 6.5+ es AGPL/comercial), QRCoder (MIT), Serilog (Apache-2.0), Microsoft.Graph / Azure.Identity / Microsoft.Identity.Web (MIT), EF Core (MIT), Microsoft.Playwright (Apache-2.0), xUnit (Apache-2.0). Fuentes: Inter y Liberation Sans (SIL OFL 1.1, licencias incluidas). Íconos: trazos estilo Lucide (ISC).

La paleta de color es **configurable** (Administración → Configuración); no se reprodujo la identidad oficial de GPV por no contar con los recursos autorizados.
