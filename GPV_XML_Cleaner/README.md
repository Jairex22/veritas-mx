# GPV XML Cleaner & Diagnostics

Herramienta interna de escritorio para Windows 11 que analiza carpetas con
grandes cantidades de archivos `.xml` (por ejemplo, resultados de
FactoryLogix / ICT / AOI), diagnostica su antigüedad y ayuda al operador a
decidir qué archivos pueden limpiarse — **sin borrar nunca nada
automáticamente**.

Construida con Python 3.14+, Tkinter (interfaz), FastAPI + Uvicorn (API
local de solo lectura) y librerías estándar. No requiere Node.js, React,
Docker, Git ni permisos de administrador. Pensada para convertirse en un
`.exe` portable con PyInstaller.

## Versión CLI standalone (sin GUI)

`GPV_XML_Cleaner_xmldiagnostic.py`, en la raíz del proyecto, es una
herramienta de **solo diagnóstico** independiente: un único archivo, sin
Tkinter, sin FastAPI, sin ninguna dependencia de terceros. Recorre
recursivamente una carpeta FLX (`Machine/Project/Process|Unprocess/*.xml`),
identifica máquina/proyecto/categoría por cada XML, calcula el más
viejo/nuevo global, por máquina, por proyecto y por combinación
máquina+proyecto, y exporta automáticamente un CSV a
`%USERPROFILE%\Downloads`. Nunca modifica, mueve ni elimina ningún XML.

```cmd
python GPV_XML_Cleaner_xmldiagnostic.py
python GPV_XML_Cleaner_xmldiagnostic.py "C:\FactoryLogix\FLX"
```

---

## 1. Arquitectura

```text
GPV_XML_Cleaner/
│
├── main.py                # Punto de entrada (python main.py)
├── requirements.txt
├── README.md
│
├── app/
│   ├── __init__.py
│   ├── gui.py              # Interfaz Tkinter completa (App)
│   ├── scanner.py          # Escaneo de carpetas XML (os.scandir, métricas)
│   ├── cleanup.py          # Simulación, movimiento seguro, export CSV
│   ├── statistics.py       # Estadísticas, growth analysis, health status
│   ├── models.py           # XMLFileInfo, ScanResult, helpers de formato
│   ├── config.py           # settings.json, logging, rutas (dev/exe)
│   └── api.py              # FastAPI (127.0.0.1:8765), solo lectura
│
├── data/
│   └── settings.json        # Configuración persistente
│
└── logs/
    └── xml_cleaner.log       # Se genera automáticamente
```

Cuando la app corre como `.exe` (PyInstaller `--onefile`), `data/` y
`logs/` se crean **junto al ejecutable real**, no dentro de la carpeta
temporal de extracción — así la configuración y los logs sobreviven entre
ejecuciones (ver `app/config.py::get_base_dir`).

---

## 2. Funcionalidad implementada

- **Pensada para carpetas FLX**: seleccionas la carpeta raíz `FLX` (que
  contiene todos tus proyectos, cada uno con sus subcarpetas `Process` /
  `Unprocess`) y la app lee automáticamente TODOS los proyectos de adentro,
  sin necesidad de marcar ninguna casilla — el escaneo siempre es completo
  y recursivo. También reconoce variantes comunes del nombre
  (`Processed`, `Procesado`, `Unprocessed`, `Sin Procesar`, etc.) y sigue
  funcionando igual con cualquier otra carpeta que no tenga esa estructura.
- Pestaña **📊 Proyectos** (la primera que se ve): una tabla simple con
  cada proyecto y cuántos XML tiene en Process, en Unprocess y en total —
  doble clic abre esa carpeta en el Explorador.
- Selección de carpeta (`askdirectory`) con análisis automático.
- Escaneo con `os.scandir()` (metadatos únicamente, nunca se lee el
  contenido del XML), en un hilo separado (`threading`) para que la
  interfaz **nunca se congele**, con barra de progreso, porcentaje y botón
  **Cancelar análisis**.
- Dashboard con 4 tarjetas grandes y fáciles de leer: XML totales, EN
  PROCESS, SIN PROCESAR y espacio usado.
- Panel **EL MÁS VIEJO** y panel **EL MÁS NUEVO (el último)**, siempre
  visibles, cada uno con botón **📂 Abrir ubicación**
  (`explorer /select,`), manejando rutas con espacios correctamente.
- Tabla completa (pestaña "Tabla de Archivos", `ttk.Treeview`) ordenable
  por columna, con scroll vertical y horizontal, coloreada por estado
  (verde/amarillo/naranja/rojo), filtros predefinidos, rango de fechas, y
  búsqueda instantánea por nombre/ruta.
- **Cleanup Advisor**: recomendación `KEEP` / `REVIEW` / `CLEANUP
  CANDIDATE` basada solo en antigüedad, fecha de modificación y tamaño
  (nunca en el contenido del archivo). Simulador de limpieza en vivo
  (sin tocar el disco) y botón **🔍 Analizar limpieza** con resumen
  detallado.
- Panel **10 Oldest XML Files** y **Folder Cleanup Ranking** (por
  subcarpeta), siempre activos.
- **🧹 Limpiar XML antiguos**: flujo de limpieza con doble confirmación
  (`Cancelar` / `Ver archivos` / `Continuar`, luego confirmación final).
  **SAFE MODE** está activo por defecto: los archivos se **mueven** a
  `XML_Archive/` (preservando subcarpetas) en lugar de eliminarse. La
  carpeta `XML_Archive` queda automáticamente excluida de futuros
  escaneos/conteos. Solo si el operador desactiva explícitamente tanto
  *SAFE MODE* como *"Mover en lugar de eliminar"* se habilita el borrado
  permanente, que exige además escribir la palabra `ELIMINAR` para
  confirmar.
- Pestaña **Statistics**: totales, tamaño promedio, XML por
  día/semana/mes, **Folder Growth Analysis** (promedio de XML generados
  por día/hora/minuto y proyección de espacio a +1/+7/+30 días,
  claramente marcada como aproximada) y **Folder Health**
  (`HEALTHY` / `WARNING` / `CRITICAL`) según reglas configurables.
  Gráfico opcional con `matplotlib` (la app funciona igual sin
  instalarlo).
- **Exportar reporte**: CSV (`xml_diagnostic_<fecha>.csv`) + resumen en
  texto plano.
- **API local de solo lectura** en `http://127.0.0.1:8765` (puerto
  configurable). Ningún endpoint permite borrar o mover archivos.
- Configuración editable desde la interfaz (`⚙ Configuración`), guardada
  en `data/settings.json`.
- Logging automático de cada operación relevante en
  `logs/xml_cleaner.log`.
- Manejo robusto de errores: carpeta inexistente, sin permisos, archivos
  bloqueados/eliminados durante el escaneo, carpeta vacía, cero XML,
  errores al mover archivos — la aplicación nunca se cierra
  abruptamente.

---

## 3. Requisitos

- Windows 11 (probado también en Linux/macOS para desarrollo).
- Python 3.14+ (compatible desde 3.10+).
- Sin permisos de administrador.

Instalar dependencias:

```cmd
cd GPV_XML_Cleaner
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

`matplotlib` es **opcional**: si no está instalado, la pestaña
Statistics simplemente muestra "Gráfico no disponible" en vez del
gráfico, sin afectar el resto de la aplicación.

---

## 4. Ejecutar en Windows (CMD)

```cmd
cd GPV_XML_Cleaner
venv\Scripts\activate
python main.py
```

Al iniciar:
1. Se crean automáticamente `data\settings.json` (si no existe) y
   `logs\xml_cleaner.log`.
2. Se levanta la API local en `http://127.0.0.1:8765` en un hilo en
   segundo plano.
3. Se abre la ventana principal (1200x750). Selecciona una carpeta con
   `📁 Seleccionar carpeta` y el análisis comienza automáticamente.

---

## 5. Crear el ejecutable portable (.exe)

Instala PyInstaller (ya incluido en `requirements.txt`) dentro del mismo
entorno virtual donde probaste `python main.py`:

```cmd
pip install pyinstaller
```

### Comando recomendado

FastAPI/Uvicorn y Tkinter usan importaciones dinámicas que el analizador
estático de PyInstaller no siempre detecta solo. El siguiente comando ya
incluye los ajustes necesarios para que el `.exe` arranque sin errores de
"No module named …":

```cmd
pyinstaller --noconsole --onefile --name GPV_XML_Cleaner ^
    --collect-all fastapi ^
    --collect-all starlette ^
    --collect-all pydantic ^
    --collect-all pydantic_core ^
    --collect-submodules uvicorn ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import uvicorn.lifespan.off ^
    --hidden-import anyio._backends._asyncio ^
    --hidden-import click ^
    --hidden-import h11 ^
    main.py
```

(El símbolo `^` es el salto de línea de CMD; también se puede escribir
todo en una sola línea sin `^`.)

Si instalaste `matplotlib` y quieres que el `.exe` incluya los gráficos
de la pestaña Statistics, agrega también:

```cmd
    --collect-all matplotlib
```

El ejecutable resultante queda en `dist\GPV_XML_Cleaner.exe`. Es
portable: cópialo a cualquier equipo Windows 11 y ejecútalo directamente
(sin instalador, sin permisos de administrador). En el primer arranque
creará automáticamente, junto al `.exe`, las carpetas `data\` y `logs\`.

### Notas sobre la configuración de PyInstaller aplicadas en el código

- `app/config.py` detecta `sys.frozen` para usar la carpeta del propio
  `.exe` (no la carpeta temporal `_MEIPASS`) como base de `data/` y
  `logs/`, para que la configuración y los logs persistan entre
  ejecuciones del portable.
- El servidor Uvicorn se ejecuta llamando directamente a
  `uvicorn.Server(...).run()` en un hilo (nunca `uvicorn.run()` por CLI
  ni `--reload`), evitando el uso de `multiprocessing`/subprocesos que
  suelen romperse dentro de un `--onefile`.
- `requirements.txt` usa `uvicorn` estándar (sin los extras
  `uvicorn[standard]`, que añaden `uvloop`/`httptools`, binarios no
  disponibles/no necesarios en Windows para este caso de uso), lo que
  simplifica el empaquetado.

---

## 6. API local (solo lectura)

Base: `http://127.0.0.1:8765` (puerto configurable en `⚙ Configuración`).
Ningún endpoint admite borrar o mover archivos; todos son `GET`.

| Endpoint             | Descripción                                            |
|-----------------------|--------------------------------------------------------|
| `GET /`               | `{"application": "...", "status": "running"}`          |
| `GET /status`         | Estado general, si hay un escaneo en curso, carpeta actual |
| `GET /folder`         | Carpeta actual + totales básicos                        |
| `GET /stats`          | Totales, tamaño, antigüedad máxima, grupos de antigüedad |
| `GET /oldest`         | Detalle del XML más antiguo                             |
| `GET /newest`         | Detalle del XML más reciente                             |
| `GET /files?limit=&offset=` | Listado paginado de archivos (metadatos)          |
| `GET /cleanup-analysis` | Mismo cálculo que "🔍 Analizar limpieza"               |

---

## 7. Estructura de `data/settings.json`

```json
{
    "retention_days": 30,
    "safe_mode": true,
    "move_instead_of_delete": true,
    "archive_folder": "XML_Archive",
    "recent_days": 7,
    "warning_days": 30,
    "critical_days": 90,
    "api_port": 8765,
    "api_host": "127.0.0.1",
    "health_warning_old_ratio": 0.25,
    "health_critical_old_ratio": 0.5,
    "health_warning_size_gb": 10.0,
    "health_critical_size_gb": 25.0,
    "last_folder": ""
}
```

`recent_days` / `warning_days` / `critical_days` controlan los colores de
diagnóstico (verde/amarillo/naranja/rojo) y, junto con `retention_days`,
la recomendación de limpieza. Todo editable desde **⚙ Configuración** sin
reiniciar la aplicación.

---

## 8. Logs

`logs/xml_cleaner.log` registra, con timestamp:

```text
2026-09-21 09:20:31 | INFO | Scan started
2026-09-21 09:20:31 | INFO | Folder selected: C:\FactoryLogix\FinalTest\XML
2026-09-21 09:20:33 | INFO | XML found: 18542
2026-09-21 09:20:33 | INFO | Oldest: test_001.xml
2026-09-21 09:20:33 | INFO | Scan finished in 1.82 seconds
```

También registra simulaciones de limpieza, archivos movidos/eliminados,
errores de acceso y el cierre de la aplicación.

---

## 9. Seguridad de los datos

- Ningún XML se elimina automáticamente. Todas las acciones destructivas
  requieren pasos de confirmación explícitos del operador.
- **SAFE MODE** (activado por defecto) siempre mueve los archivos a
  `XML_Archive/` en vez de borrarlos.
- El borrado permanente solo es alcanzable si el operador desactiva
  manualmente **ambas** protecciones (SAFE MODE y "mover en lugar de
  eliminar") y además escribe `ELIMINAR` en el cuadro de confirmación.
- La API es de **solo lectura**: no existe ningún endpoint capaz de
  borrar, mover o modificar archivos.
