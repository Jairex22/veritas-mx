# GPV FactoryLogix Command Center v1.0

Aplicación web industrial para **GPV Americas**: trazabilidad, diagnóstico inteligente de rework,
operaciones controladas, packing, control de etiquetas y Production Intelligence sobre FactoryLogix.

* **Backend:** Python 3.10+ · FastAPI · Uvicorn · SQLite propia (separada de FactoryLogix).
* **Frontend:** HTML + CSS + JavaScript (ES modules) **sin compilación**, servido por el mismo backend.
  Sin npm, Docker, CDN ni instalación en estaciones: se usa desde cualquier navegador corporativo.
* **Modos:** `DEMO` (datos sintéticos, operaciones simuladas) y `REAL` (sólo fuentes reales, solo lectura).

> ⚠️ **Estado de integración:** ninguna transacción de escritura en FactoryLogix está habilitada en v1.0.
> No se verificaron métodos xTend (la documentación oficial no fue accesible desde el entorno de desarrollo)
> y no se inventaron endpoints. Ver [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md).

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
| Rework inteligente (8 reglas) | Funcional |
| Centro de Operaciones | Flujo completo **simulado** en DEMO; **NO DISPONIBLE** en REAL |
| Packing Intelligence | Validación funcional; empaque simulado en DEMO |
| Label Control | Previsualización y control de reimpresión funcionales; impresión **simulada** |
| Conectores (OData, xTend, FactoryLogixAPI, archivos) | Pruebas de conexión y diagnóstico funcionales; lectura OData requiere mapeo |
| Auditoría | Funcional (cadena SHA-256 verificable) |

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
