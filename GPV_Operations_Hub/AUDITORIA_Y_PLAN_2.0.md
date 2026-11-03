# GPV Operations HUB 2.0 · Fase 1: auditoría y plan de migración incremental

Fecha: 2026-11-03 · Base auditada: v1.1.0 (rama `claude/great-shannon-y0f3cd`) · Entregado en esta
iteración: Fases 1, 2 y 3 (parcial: el descubrimiento real requiere ejecutar el diagnóstico en la red de GPV).

## 1. Diagnóstico de la aplicación existente

| Aspecto | Hallazgo |
|---|---|
| Framework | Python 3.11–3.13 · Django 5.2.18 LTS · plantillas del servidor + JavaScript propio sin *bundler* (sin npm/npx) |
| Base de datos | SQLite (WAL) para el piloto; PostgreSQL 16 probado. ORM de Django, 13 aplicaciones, migraciones al día |
| Despliegue | `runserver 127.0.0.1` en el equipo (INSTALAR/INICIAR.bat), Waitress opcional; sin Docker ni privilegios de administrador |
| Autenticación | Usuarios de Django (contraseña), sesión con cookie, CSRF, CSP `script-src 'self'` |
| Autorización | Matriz de capacidades por rol configurable en BD + filtro por área en el servidor (`apps/core/permissions.py`) |
| Roles | Admin, Supervisor, Ingeniero, Operador → **se agrega Técnico** (2.0) |
| Módulos existentes (se conservan) | Comunicados, Producción (plan/import Excel-CSV), Dashboard y reportes (PDF/XLSX/CSV/DOCX/PPTX), Hoja de cálculo, Documentos, Etiquetas, Kaizen, Portal del turno SMT, Administración, respaldo/restauración |
| Componentes reutilizables | Capa de métricas común, exportadores, cola de trabajos con progreso, planificador con *lease*, auditoría, notificaciones internas, archivos privados, `GPV.api` / formularios con trabajo |
| Integración previa | `apps/shift/odata.py`: sincronización OData de solo lectura del portal del turno (eventos de producción para una línea) |
| Rendimiento medido | Pantallas del turno ≈ 0.45 s con 10 000 eventos de conteo; 10 usuarios simultáneos sin errores (p95 1.1 s) en SQLite |
| Pruebas | 121 pruebas automáticas (SQLite/PostgreSQL, Python 3.11–3.13), E2E Playwright de escritorio y móvil |
| Problemas conocidos | Sin conexión real a FactoryLogix; no ejecutado aún en Windows 11 de GPV; modo oscuro no implementado; pantallas densas en algunos módulos de analistas |

## 2. Decisiones de arquitectura

* **Se mantiene el stack** (Django + plantillas + JS propio): funciona sin npm, sin Docker y sin
  privilegios, que son restricciones reales del equipo de GPV. Reescribir en ASP.NET Core no aporta
  valor verificable en esta etapa y pondría en riesgo los módulos existentes.
* **Nueva capa de integración `apps/flx`** (FactoryLogix), independiente de la vista:

```
Navegador (sin acceso a OData ni credenciales)
   ↓  sesión + CSRF
Vistas / API del portal  ──  autorización por capacidad (flx.status, flx.query, flx.admin) y rol
   ↓
Motor de consultas controladas (query.py): lista permitida = esquema real + capacidades verificadas
   ↓
Cliente OData de solo lectura (client.py): URL fija por configuración, GET únicamente,
   reintentos limitados, circuit breaker, límite de concurrencia, caché corta, logs sin encabezados
   ↓
FactoryLogix OData  http://10.62.54.10:6065/odata/  (red interna de GPV)
```

* Datos propios del portal (capturas, pendientes, reportes) siguen en la base local; **nunca** se
  escribe en FactoryLogix ni en su base de datos.
* El conector del portal del turno (`apps/shift/odata.py`) se unificará con `apps/flx/client.py`
  en la Fase 4, cuando se conozcan las entidades reales que alimentan producción.

## 3. Plan de migración incremental

| Fase | Contenido | Estado | Depende de |
|---|---|---|---|
| 1 | Auditoría y plan | **Hecho** (este documento) | — |
| 2 | Conector OData solo lectura, autenticación (anónimo/Basic/Windows integrada/NTLM), diagnóstico por etapas, FactoryLogix Connection Center, CLI `flx_diagnose` | **Hecho y probado con servidor simulado** | — |
| 3 | Descubrimiento de esquema ($metadata v2/v4, claves, navegación, FunctionImports, anotaciones de capacidades), registro de entidades, sondeo controlado `$top=1`, prueba de capacidades por entidad, motor de consultas controladas con paginación real | **Implementado y probado con simulado**; **pendiente ejecutar en la red de GPV** | Acceso desde un equipo de GPV |
| 4 | Dashboard general, Serial Intelligence, Smart Work Order Center | Pendiente | Esquema real y estados de la Fase 3 |
| 5 | Quality Intelligence, SMT Live Monitor | Pendiente | Ídem; definición de indicadores con GPV |
| 6 | Loop Detector, generador de reportes con procedencia, capturas del operador ligadas a seriales/órdenes | Pendiente (capturas ya existen en el portal del turno) | Fases 3–4 |
| 7 | GPV AI Assistant con herramientas permitidas; modo local sin IA externa por defecto | Pendiente | Aprobación de GPV para IA externa (si aplica) |
| 8 | Optimización, accesibilidad WCAG 2.2 AA, modo oscuro, pruebas y documentación finales | Pendiente | Fases 4–7 |

**Por qué no se construyeron aún los tableros de las Fases 4–5:** sus cálculos dependen de
propiedades reales (orden, serial, estación, resultado, fechas) que solo el `$metadata` y respuestas
válidas de FactoryLogix pueden confirmar. Construirlos con nombres supuestos produciría pantallas que
parecen funcionar y no lo hacen. El primer paso operativo es ejecutar el diagnóstico en la red de GPV.

## 4. Siguiente paso concreto para GPV

1. En el equipo Windows 11 de GPV (en la red interna), dentro de la carpeta con `manage.py`:
   doble clic en `DIAGNOSTICO_FACTORYLOGIX.bat` (o `manage.py flx_diagnose`).
2. Si el servidor exige autenticación, el reporte dirá qué métodos ofrece (p. ej. Negotiate/NTLM o
   Basic). Configure el método indicado (ver `FACTORYLOGIX_CONNECTION_CENTER.md`) y repita.
3. Con autorización del administrador MES, repita con sondeo controlado (`$top=1` por EntitySet).
4. Comparta el reporte `data\diagnosticos\diagnostico_factorylogix_*.json` (estructura y estados, sin
   valores de registros ni credenciales) o el `$metadata` XML para diseñar las Fases 4–5 sobre campos reales.
