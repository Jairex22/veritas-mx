# Diagnóstico, respaldo y restauración

## Diagnóstico

Web: Administración › Diagnóstico. Terminal:

```bat
.venv\Scripts\python.exe manage.py gpv_diagnose
```

Verifica: versión de Python, zona horaria (`tzdata`), modo DEBUG, datos demo, conexión a base de
datos, migraciones pendientes, escritura en carpetas privadas/temporales/respaldos/logs, recursos
estáticos, LibreOffice, pypdfium2, Tesseract (opcional), lector de códigos (opcional), modo de
trabajos y trabajos atascados o fallidos (24 h), planificador activo (lease) e impresoras
(validada/habilitada). Termina con código 1 si hay errores.

Logs: `data\logs\gpvhub.log` (rotación 5 × 5 MB). Cada línea lleva un ID de operación; los errores
mostrados al usuario incluyen «Referencia para soporte: <id>» para buscarlo en el log. No se registran
contraseñas ni contenidos de archivos.

Otras herramientas:

```bat
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py check --deploy          (perfil prod)
.venv\Scripts\python.exe manage.py cleanup_temp --hours 24
.venv\Scripts\python.exe manage.py run_worker --once        (procesa la cola y termina)
.venv\Scripts\python.exe manage.py run_scheduler --once     (un ciclo del planificador)
```

## Respaldo

```bat
.venv\Scripts\python.exe manage.py gpv_backup
.venv\Scripts\python.exe manage.py gpv_backup --output D:\respaldos\gpv_2026-11-02.zip
```

El ZIP contiene:

* `database.json`: todos los datos en formato portable (SQLite ↔ PostgreSQL), incluidos usuarios,
  permisos, plantillas de etiquetas, dashboards, reportes, hojas, Kaizen y auditoría.
* `private/…`: archivos privados (originales importados, documentos, reportes, etiquetas, adjuntos).
* `manifest.json`: hash SHA-256 de la base y de cada archivo.

Recomendación: tarea programada diaria y copia del ZIP fuera del servidor. Para bases grandes en
PostgreSQL, TI puede complementar con `pg_dump` (el ZIP sigue siendo necesario para los archivos).

## Restauración (probada)

```bat
.venv\Scripts\python.exe manage.py gpv_restore data\backups\gpv_backup_20261102_101500.zip --confirmar
```

1. Verifica los hashes del manifiesto (rechaza respaldos dañados o con rutas inválidas).
2. Aplica migraciones, vacía la base y carga los datos en una transacción.
3. Reemplaza la carpeta de archivos privados; la anterior queda en `data\private_before_restore`.

Detenga trabajador y planificador antes de restaurar y reinícielos después. La prueba automatizada
`apps/core/tests/test_backup.py` crea datos y un archivo, respalda, borra, restaura y descarga el
archivo con verificación de contenido (en SQLite y PostgreSQL).
