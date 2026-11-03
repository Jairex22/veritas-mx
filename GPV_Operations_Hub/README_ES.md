# GPV Operations HUB 2.0 (fases 1–3) · Portal del turno + conector FactoryLogix

> **2.0 · estado de esta entrega:** Fase 1 (auditoría, `AUDITORIA_Y_PLAN_2.0.md`), Fase 2 (conector
> OData de solo lectura, autenticación, **FactoryLogix Connection Center**, diagnóstico por etapas) y
> Fase 3 (descubrimiento de esquema, sondeo controlado, capacidades por entidad, motor de consultas
> controladas). Todo probado contra un servidor OData **simulado**: el servidor real
> `http://10.62.54.10:6065/odata/` es de la red interna de GPV y **debe diagnosticarse desde allí**
> (`DIAGNOSTICO_FACTORYLOGIX.bat`, ver `FACTORYLOGIX_CONNECTION_CENTER.md`). Las Fases 4–8 (dashboards,
> seriales, órdenes, calidad, SMT, Loop Detector, reportes, asistente) se construirán sobre los campos
> reales que ese diagnóstico confirme.

> **Importante al extraer el ZIP:** «Extraer todo» crea `GPV_Operations_HUB_2.0\GPV_Operations_HUB_2.0\`.
> Trabaje en la carpeta **interior** (la que contiene `manage.py`). En PowerShell:
> `cd "$HOME\Downloads\GPV_Operations_HUB_2.0\GPV_Operations_HUB_2.0"` y verifique con `dir manage.py`.


Sitio web interno en español (Edge/Chrome y celular) para el trabajo diario del turno en GPV
Americas, más las herramientas existentes de producción, comunicados, datos, documentos, etiquetas
y Kaizen. Servidor Python + Django; **no depende de Claude ni de APIs de IA**: los cálculos son
deterministas y verificables.

> Estado: portal del turno implementado y probado con **datos sintéticos** y un servicio OData
> **simulado**. La conexión a FactoryLogix real está **pendiente de acceso de GPV** (URL, cuenta de
> lectura, `$metadata`). No participó personal real en las pruebas. Ver `PRUEBAS_Y_RESULTADOS.md`
> y `DECISIONES_PENDIENTES.md`.

## Inicio en Windows (equipo del piloto)

Requiere Python 3.11, 3.12 o 3.13 (sin privilegios de administrador). Al extraer
`GPV_Operations_HUB_2.0.zip`, entre a la carpeta que contiene `manage.py` (la interior).

**Sin terminal:** doble clic en `INSTALAR.bat` (una vez) y después en `INICIAR.bat` (cada día).

**Con terminal (PowerShell o CMD), un comando a la vez, dentro de la carpeta con `manage.py`:**

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py seed_demo
start "GPV servicio del turno" /min .venv\Scripts\python.exe manage.py run_scheduler
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abra **http://127.0.0.1:8000/** en Edge o Chrome. `seed_demo` es opcional: crea datos **sintéticos**,
la línea **SMT-EJEMPLO**, usuarios de prueba (muestra la contraseña una vez) y una fuente OData
**SIMULADA**; para usarla abra también `INICIAR_ODATA_SIMULADO.bat`.

* `127.0.0.1` solo es accesible **desde el mismo equipo**. El acceso desde otras estaciones requiere
  un despliegue interno autorizado (`DESPLIEGUE_INTERNO.md`). No se cambia el firewall ni se escucha
  en todas las interfaces.
* **Puerto ocupado:** use otro, p. ej. `runserver 127.0.0.1:8001`, y abra `http://127.0.0.1:8001/`.
* **Sin red de GPV:** el portal y la captura web funcionan; la fuente OData aparece «Desconectado»
  y se conservan los últimos datos con su antigüedad.

## Procesos (qué debe quedar abierto)

| Proceso | Comando | Necesario para |
|---|---|---|
| Sitio web | `manage.py runserver 127.0.0.1:8000` | Siempre |
| Servicio del turno | `manage.py run_scheduler` (INICIAR.bat lo abre minimizado) | Sincronización OData de solo lectura cada 60 s, recordatorios/escalamientos internos, borradores de reporte y relevo al fin de turno, reportes programados |
| Trabajador (opcional) | `manage.py run_worker` | Solo si `GPV_JOBS_MODE=worker` |
| Diagnóstico FactoryLogix (a demanda) | `DIAGNOSTICO_FACTORYLOGIX.bat` o `manage.py flx_diagnose` | En un equipo de la red de GPV; luego ver **FactoryLogix** en el menú (`/factorylogix/`) |

Detener: cierre las ventanas o `Ctrl+C`. Si el equipo se suspende o apaga, las tareas se detienen;
al volver se informa la laguna y se generan **una vez** los borradores pendientes
(`RESPALDO_RESTAURACION_Y_SOPORTE.md`).

## Dónde se guardan los datos

| Qué | Dónde |
|---|---|
| Base SQLite | `data\gpvhub.sqlite3` (o `GPV_DATA_DIR`) |
| Archivos privados (fotos, evidencias, PDF) | `data\private\` |
| Registros | `data\logs\` |
| Respaldos | `data\backups\` (`manage.py gpv_backup`) |
| Credenciales OData | **Solo** variables de entorno del usuario de Windows (`CONFIGURACION_ODATA.md`) |

SQLite (modo WAL) es adecuado para el piloto en un equipo con pocos usuarios simultáneos; no se le
atribuye capacidad empresarial. Para uso compartido permanente se prevé PostgreSQL 16 en un
servidor administrado por GPV (`DESPLIEGUE_INTERNO.md`; probado en las pruebas automatizadas).

## Portal del turno (menú «Mi turno»)

Mi turno (contexto y siguiente acción) · Ver mi trabajo · Necesito ayuda · Imprimir etiqueta ·
Revisar cierre de turno · Paros · Materiales · Instrucciones y listas · Calidad · Relevo ·
Supervisión · Metas · Conciliación · Fuentes · Pantalla del área. Detalle en `PILOTO_SMT.md`.

## Herramientas existentes (se conservan)

Comunicados, Producción (plan), Cargar información (Excel/CSV, opcional), Dashboard, Reportes,
Hoja de cálculo, Documentos, Etiquetas (diseñador completo), Kaizen y Administración. Ver
`GUIA_USUARIO_ES.md`.

## Documentación

| Documento | Contenido |
|---|---|
| `AUDITORIA_Y_PLAN_2.0.md` | Auditoría del proyecto, arquitectura y plan incremental de las fases 1–8 |
| `FACTORYLOGIX_CONNECTION_CENTER.md` | Diagnóstico en la red de GPV, autenticación, estados, consultas controladas |
| `ENDPOINTS_API.md` | Endpoints de la aplicación |
| `PILOTO_SMT.md` | Alcance, pantallas, preparación y guion del piloto |
| `GUIA_OPERADOR.md` / `GUIA_ADMINISTRACION.md` | Uso diario y administración |
| `CONFIGURACION_ODATA.md` | Autenticación, diagnóstico por etapas, mapeo, refresco |
| `FUENTES_Y_MAPEOS.md` | Fuentes, campos, claves y estado de cada integración |
| `CONCILIACION_CAPTURA_ODATA.md` | Reglas de conciliación y conteo |
| `DEFINICIONES_DE_DATOS_Y_KPI.md` | Definiciones y fórmulas |
| `CONFIGURACION_TURNOS_Y_ROLES.md` | Turnos, descansos, roles, grupos, líneas y estaciones |
| `ACTUALIZACION_Y_REVERSIÓN.md` | Actualizar desde v1.0.x conservando datos y cómo revertir |
| `RESPALDO_RESTAURACION_Y_SOPORTE.md` | Respaldo, restauración, interrupciones y soporte |
| `PRUEBAS_Y_RESULTADOS.md` | Pruebas ejecutadas, evidencia y límites |
| `DECISIONES_PENDIENTES.md` / `CHECKPOINT.md` | Lo que falta confirmar y estado del trabajo |
| `CAMBIOS.md` · `THIRD_PARTY_NOTICES.md` | Historial y licencias |
| `INSTALACION_WINDOWS.md` · `DESPLIEGUE_INTERNO.md` · `DIAGNOSTICO.md` · `LIMITACIONES.md` · `MODELO_DATOS.md` · `MATRIZ_FUNCIONAL.md` · `GUIA_USUARIO_ES.md` · `GUIA_VALIDACION_ETIQUETAS.md` | Documentación de la plataforma base |

## Estructura

```
GPV_Operations_HUB_2.0/
├─ manage.py · INSTALAR.bat · INICIAR.bat · DIAGNOSTICO_FACTORYLOGIX.bat · INICIAR_ODATA_SIMULADO.bat · .env.example
├─ gpvhub/settings/   configuración dev / prod / test
├─ apps/flx/          conector FactoryLogix: $metadata, cliente de solo lectura, sondeo, consultas controladas, Connection Center
├─ apps/shift/        portal del turno: modelo, conector OData de solo lectura, conteo/conciliación, reportes, vistas
├─ apps/core …        usuarios, roles, permisos, archivos, auditoría, notificaciones, trabajos, respaldo
├─ apps/comms, production, reports, sheets, documents, labels, kaizen
├─ templates/, static/gpv/   HTML, CSS y JS propios (sin CDN)
├─ samples/           archivos sintéticos de ejemplo
└─ tools/             servicio OData SIMULADO, E2E (Playwright, desarrollo), medición de rendimiento, empaquetado
```
