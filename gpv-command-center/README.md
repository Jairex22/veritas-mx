# GPV FactoryLogix Command Center v1.0

Aplicación web industrial para **GPV Americas**: trazabilidad, diagnóstico inteligente de rework,
operaciones controladas, packing, control de etiquetas y Production Intelligence sobre FactoryLogix.

* **Backend:** Python 3.10+ · FastAPI · Uvicorn · SQLite propia (separada de FactoryLogix).
* **Frontend:** HTML + CSS + JavaScript (ES modules) **sin compilación**, servido por el mismo backend.
  Sin npm, Docker, CDN ni instalación en estaciones: se usa desde cualquier navegador corporativo.
* **Modos:** `DEMO` (datos sintéticos, operaciones simuladas) y `REAL` (sólo fuentes reales, solo lectura).

> ⚠️ **Estado de integración:** la **lectura** real de FactoryLogix se hace vía OData con un **asistente de mapeo**
> que descubre las entidades y propiedades de su instalación (Conectores → Asistente de mapeo OData). Ninguna
> transacción de **escritura** está habilitada: no se verificaron métodos xTend (documentación oficial no accesible
> desde el entorno de desarrollo) y no se inventaron endpoints. Ver [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

## Inicio rápido (DEMO)

```bat
cd gpv-command-center
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt
scripts\run_tests.bat
scripts\run_server.bat
```

Abra `http://127.0.0.1:8080/` y entre con un rol DEMO (Operador, Ingeniería, Calidad, Administrador).

Linux/macOS: `pip install -r requirements-dev.txt && scripts/run_tests.sh && scripts/run_dev.sh`.

### Recorrido sugerido en DEMO

| Pruebe | Qué observar |
|--------|--------------|
| Dashboard | KPIs con definición (ícono ⓘ), tendencia, FPY, WIP, resumen de rework |
| Buscar `DEMO-GPV-L00001` | Bucle FCT↔Debug (×3) en el diagrama de estaciones |
| Buscar `PNL-DEMO-MIX-04` (campo Panel) | Panel con PASS y FAIL bloqueado antes de Depanel |
| Rework inteligente | 8 reglas; evidencia (HECHO) separada de hipótesis; confianza y riesgo |
| Operaciones → Registrar reparación, serial `DEMO-GPV-R00002` | Verificación previa, confirmación, comprobación posterior, auditoría |
| Operaciones → Liberar HOLD (rol Calidad), `DEMO-GPV-H00003` | Validación de defectos verificados antes de liberar |
| Packing: caja `BOX-DEMO-24102-01`, serial `DEMO-GPV-A00005` | Validación de escaneo, duplicados y discrepancias |
| Label Control | Previsualización, impresión simulada, reimpresión controlada por rol |
| Conectores | Estados veraces (NO CONFIGURADO), matriz de integraciones |
| Auditoría | Cadena de hashes íntegra, bitácora de accesos |

## Módulos

| Módulo | Estado v1.0 |
|--------|-------------|
| Login DEMO + login corporativo vía IIS (Windows Auth) | Funcional |
| Dashboard / Production Intelligence | Funcional (DEMO, OData mapeado, CSV) |
| Trazabilidad (9 campos de búsqueda, historial, flujo de estaciones, defectos, reparaciones, síntomas, componentes, escaneos, panel) | Funcional |
| Consulta directa OData (caja/serial/orden → seriales, con el $metadata real) | Funcional |
| Rework inteligente (8 reglas) | Funcional |
| Centro de Operaciones | Flujo completo **simulado** en DEMO; **NO DISPONIBLE** en REAL |
| Packing Intelligence | Validación funcional; empaque simulado en DEMO |
| Label Control | Previsualización y control de reimpresión funcionales; impresión **simulada** |
| Conectores (OData, xTend, FactoryLogixAPI, archivos) | Pruebas de conexión y diagnóstico; **asistente de mapeo OData** (descubrir → mapear → probar → activar) |
| Auditoría | Funcional (cadena SHA-256 verificable) |

## Consulta directa OData (la forma más rápida de ver datos reales)

Sin configurar nada en el servidor: entre con cualquier acceso de Ingeniería, Calidad o Administrador
(también el DEMO), abra **Consulta directa OData**, escriba la URL (p. ej. `10.62.54.10/odata`), las credenciales
si el servicio las pide, y pulse **Conectar**. Luego escanee o escriba una **caja, serial u orden**: la aplicación busca
en todas las entidades del `$metadata` real y lista los **seriales relacionados** (copiar / CSV) junto con las filas
encontradas. Sólo lectura; las credenciales viven en memoria durante la sesión y nunca se guardan.

## Conectar a FactoryLogix como fuente permanente (modo REAL, sólo lectura)

1. En `.env`: `GPV_MODE=REAL`, `GPV_REAL_DATA_SOURCE=odata`, `GPV_ODATA_BASE_URL=https://<servidor>/<ruta-odata>`,
   `GPV_ODATA_AUTH=basic|bearer|ntlm|none` y credenciales. Para entrar sin DEMO: `GPV_PROXY_AUTH_HEADER` + IIS
   (ver `docs/DEPLOYMENT.md`) o, para una prueba local, un `config/user_roles.json` y el encabezado del proxy.
2. Conectores → **Asistente de mapeo OData** → Descubrir → Mapear → Probar → Activar.
3. Alternativa CLI: `py scripts\odata_discover.py --report inventario.json`.

## Documentación

* [Arquitectura y estructura del proyecto](docs/ARCHITECTURE.md) (A, B)
* [Diseño de pantallas](docs/SCREENS.md) (C)
* [Integraciones verificadas y pendientes](docs/INTEGRATIONS.md) (D)
* [Instalación y despliegue](docs/DEPLOYMENT.md)
* [Seguridad y auditoría](docs/SECURITY.md)
* [Limitaciones y fases](docs/LIMITATIONS.md)

## Pruebas

`scripts\run_tests.bat` (o `python -m pytest -q`). Incluye pruebas que garantizan que ninguna acción DEMO
alcanza la red ni producción, que el modo REAL no devuelve datos sintéticos y que todas las acciones reales
responden NO DISPONIBLE.
