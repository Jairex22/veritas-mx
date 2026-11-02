# GPV Operations Hub v1.0.0

Sitio web interno (en español, responsive, Edge/Chrome y celular) para producción, colaboración,
datos, documentos, etiquetas y Kaizen. Los empleados entran por una URL; no se instala nada en
las computadoras cliente. El servidor es Python + Django y **no depende de Claude, de una
suscripción ni de APIs de IA**: todos los cálculos son deterministas y verificables.

> Estado: versión 1.0.0 con pruebas automatizadas y de navegador ejecutadas (ver `TEST_RESULTS.md`).
> No se declara «listo para producción» sin la validación de infraestructura corporativa,
> impresoras físicas y PostgreSQL descrita en `LIMITACIONES.md` y `DESPLIEGUE_INTERNO.md`.

## Inicio rápido (Windows, sin privilegios de administrador)

Requiere Python 3.11, 3.12 o 3.13 (verifique con `py --version`). Instrucciones detalladas y solución
de problemas en `INSTALACION_WINDOWS.md`. Desde la carpeta descomprimida, en una terminal:

```bat
py --version
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py seed_demo
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abra **http://127.0.0.1:8000/** en Edge o Chrome e inicie sesión con el administrador creado.
`seed_demo` es opcional (datos sintéticos y usuarios de prueba; muestra la contraseña una vez).
No hace falta activar el entorno (`Activate.ps1`): se invoca directamente `.venv\Scripts\python.exe`.

> Un sitio dinámico se ve **iniciando el servidor y abriendo la URL**. Abrir un `.html` con doble
> clic o con Live Server no ejecuta Django, importaciones ni la base de datos.

## Módulos

| Menú | Qué hace |
|---|---|
| Inicio | Indicadores del mes, comunicados vigentes, órdenes asignadas, trabajos recientes |
| Comunicados | Avisos por área/turno/grupo/rol con prioridad, vigencia, adjuntos y confirmación de lectura; comentarios, dudas e incidencias; conversaciones internas; notificaciones con leído/no leído (consulta periódica configurable) |
| Producción | Plan por hoy/semana/mes/rango con filtros, avance, pendiente, atraso, fuente y antigüedad; cambios de meta/prioridad con motivo e historial; captura de avance del operador asignado; proyección declarada |
| Cargar información | Asistente XLSX/CSV: detección de hojas, codificación y separador, vista previa, mapeo, claves, validación por fila/columna, modos anexar/actualizar/reemplazar alcance, snapshots, perfiles de mapeo, errores exportables, historial y reversión |
| Dashboard | KPIs, barras, tendencias, Pareto, atrasos, Kaizen; filtrado cruzado por clic; detalle de registros; exportación exacta de la selección; constructor de dashboards con campos calculados seguros y unión validada |
| Reportes | Diario, cumplimiento semanal, atrasos, calidad, por línea y Kaizen en PDF/XLSX/CSV/DOCX/PPTX desde una instantánea consistente; programación diaria/semanal/por turno con planificador dedicado |
| Hoja de cálculo | Varias hojas, edición, rangos, copiar/pegar, deshacer/rehacer, filas/columnas, ordenar, filtrar, buscar/reemplazar, congelar, anchos, formatos, formato condicional, validación, protección de columnas, agrupación, tabla dinámica, fórmulas recalculadas en el servidor, versiones y control de conflictos, publicación validada a un dataset |
| Documentos | PDF (combinar, cortar, organizar con miniaturas, rotar, duplicar, recortar, numerar, marca de agua, texto, imágenes↔PDF, texto, tablas, optimizar, desbloquear con contraseña), PPTX (organizar, extraer, duplicar, combinar preservando temas), XLSX/CSV (hojas, dividir, combinar, duplicados, limpieza, separadores, PDF de rangos), DOCX (estructura, secciones, combinar, reemplazar, plantillas, corte por páginas vía PDF), conversión Office→PDF con LibreOffice si está disponible |
| Etiquetas | Diseñador en mm (reglas, cuadrícula, zoom, guías, selección múltiple, alinear/distribuir, capas, bloqueo, deshacer), texto, campos variables, imágenes, líneas, rectángulos, QR y Code 128; plantillas JSON versionadas; vista previa con datos reales; PDF/SVG a escala y ZPL; impresión por navegador o impresoras registradas; consecutivos transaccionales; reimpresión con permiso y motivo; estados honestos |
| Kaizen | Registro, flujo propuesta→evaluación→aprobada→implementación→verificación→cerrada/rechazada, 5 porqués, PDCA, acciones, antes/después con periodos y fuente, ahorros con fórmula y aprobación, A3 en PDF |
| Administración | Usuarios, roles, áreas, turnos, matriz de permisos, logotipo, diagnóstico, auditoría, impresoras y contadores |

## Procesos

| Proceso | Comando | Cuándo |
|---|---|---|
| Sitio web | `manage.py runserver 127.0.0.1:8000` (local) / `waitress-serve` (interno) | Siempre |
| Trabajador | `manage.py run_worker` | Si `GPV_JOBS_MODE=worker` (recomendado para uso compartido) |
| Planificador | `manage.py run_scheduler` | Si usa reportes programados (una sola instancia) |

## Estructura del proyecto

```
GPV_Operations_Hub_v1.0.0/
├─ manage.py                 · comandos de Django
├─ gpvhub/settings/          · configuración dev / prod / test (lee .env)
├─ apps/core                 · usuarios, roles, permisos, archivos privados, auditoría, notificaciones, trabajos, diagnóstico, respaldo
├─ apps/comms                · comunicados, comentarios, incidencias, conversaciones
├─ apps/production           · datasets, importación, plan, registros, capa de métricas
├─ apps/reports              · dashboards, constructor, reportes, exportadores, planificador
├─ apps/sheets               · hoja de cálculo y motor de fórmulas
├─ apps/documents            · centro de documentos y operaciones PDF/Office
├─ apps/labels               · diseñador, render SVG/PDF/ZPL, Code 128, impresión
├─ apps/kaizen               · mejoras, A3
├─ templates/, static/gpv/   · HTML, CSS, JS e iconos propios (sin CDN)
├─ samples/                  · archivos sintéticos de ejemplo y plantillas de etiquetas
├─ tools/                    · E2E (Playwright, solo desarrollo), prueba de carga, empaquetado
├─ scripts/                  · atajos .bat opcionales
└─ *.md                      · documentación
```

## Documentación

`INSTALACION_WINDOWS.md` · `DESPLIEGUE_INTERNO.md` · `GUIA_USUARIO_ES.md` · `GUIA_VALIDACION_ETIQUETAS.md` ·
`MODELO_DATOS.md` · `DEFINICIONES_KPI.md` · `MATRIZ_FUNCIONAL.md` · `LIMITACIONES.md` · `TEST_RESULTS.md` ·
`DIAGNOSTICO.md` · `CHANGELOG.md` · `THIRD_PARTY_NOTICES.md` · `CHECKPOINT.md`
