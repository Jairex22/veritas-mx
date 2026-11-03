# Instalación en Windows (prueba local)

Diseñado para Windows corporativo **sin** npm, Node, Docker, Git, instaladores ni scripts PowerShell.
Solo se necesita Python (3.11, 3.12 o 3.13) permitido por TI. No se requieren privilegios de
administrador. No se desactiva ninguna política de seguridad.

## 1. Descomprimir y ubicar la carpeta correcta

1. Clic derecho sobre `GPV_SMT_Portal_Turno_Piloto.zip` › **Extraer todo…** › **Extraer**.
2. **Importante:** Windows crea una carpeta con el nombre del ZIP y, dentro, está la carpeta del
   proyecto con el mismo nombre. La carpeta correcta es la que contiene `manage.py`, `INSTALAR.bat`
   y `requirements.txt`. Si extrajo en Descargas, la ruta queda así:

   `C:\Users\SU_USUARIO\Downloads\GPV_SMT_Portal_Turno_Piloto\GPV_SMT_Portal_Turno_Piloto`

### Opción A — sin terminal (recomendada)

Abra la carpeta que contiene `manage.py` y haga **doble clic en `INSTALAR.bat`**. Instala, prepara la
base, le pide crear el administrador y, si quiere, carga datos de demostración. Después haga doble
clic en **`INICIAR.bat`**: abre el navegador en http://127.0.0.1:8000/ y, minimizada, la ventana «GPV servicio del turno». Deje ambas abiertas.
Si su organización bloquea archivos `.bat`, use la opción B.

### Opción B — terminal (PowerShell o Símbolo del sistema)

Ubíquese en la carpeta del proyecto. En PowerShell, este comando la encuentra sola dentro de Descargas
(no hay que escribir el nombre de usuario):

```powershell
cd (Get-ChildItem "$HOME\Downloads" -Recurse -Filter manage.py -ErrorAction SilentlyContinue | Where-Object { $_.DirectoryName -like "*GPV_SMT_Portal_Turno_Piloto*" } | Select-Object -First 1).DirectoryName
```

Compruebe que está en el lugar correcto (deben listarse ambos archivos):

```powershell
dir manage.py, requirements.txt
```

Si aparece «No se encuentra la ruta», no continúe: vuelva a ubicar la carpeta interna.
En Visual Studio Code: **Archivo › Abrir carpeta…** › elija la carpeta interna; la terminal integrada
ya abre en ella.

## 2. Comprobar Python

```bat
py --version
```

Debe mostrar `Python 3.11.x`, `3.12.x` o `3.13.x`. Si `py` no existe, pruebe `python --version`
y use `python` en lugar de `py` en el paso 3. Si no hay Python, solicítelo a TI (no lo instale
evadiendo políticas).

## 3. Crear el entorno aislado

```bat
py -m venv .venv
```

## 4. Instalar requisitos (núcleo)

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Opcional (servidor WSGI para Windows y lector de códigos para verificar etiquetas):

```bat
.venv\Scripts\python.exe -m pip install -r requirements-optional.txt
```

Todas las dependencias tienen ruedas precompiladas para Windows x64 y Python 3.11–3.13
(verificado con `pip download --only-binary=:all: --platform win_amd64`; ver `TEST_RESULTS.md`).

## 5. Configuración

```bat
copy .env.example .env
```

Para la prueba local los valores por defecto sirven (SQLite, modo de trabajos `inline`, datos de
demostración permitidos). La clave secreta de desarrollo se genera sola en `data\dev_secret_key.txt`.

## 6. Preparar la base de datos

```bat
.venv\Scripts\python.exe manage.py migrate
```

## 7. Crear el administrador

```bat
.venv\Scripts\python.exe manage.py createsuperuser
```

Escriba usuario, correo (solo referencia) y contraseña (mínimo 10 caracteres).
Para cambiar la contraseña después: menú de usuario › **Cambiar contraseña**, o
`.venv\Scripts\python.exe manage.py changepassword <usuario>`.

## 8. (Opcional) Cargar datos de demostración sintéticos

```bat
.venv\Scripts\python.exe manage.py seed_demo
```

Crea áreas (SMT, ENS, PRU, EMP), turnos (T1–T3), usuarios de prueba (`supervisor1`, `ingeniero1`,
`operador1`, `lector1`) con una contraseña aleatoria que se muestra **una sola vez** (o use
`--password ...`), datasets, importa los archivos de `samples/` por el asistente real, plantillas
de etiquetas, Kaizen, un dashboard y documentos de muestra. Para no crear usuarios: `--sin-usuarios`.

## 9. Verificar e iniciar

```bat
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py gpv_diagnose
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abra **http://127.0.0.1:8000/** en Edge o Chrome. Para detener el servidor: `Ctrl+C` en la terminal.
Para reanudar: repita solo el comando `runserver`.

Atajo opcional: `scripts\iniciar_local.bat` (si su organización permite archivos .bat).

## 10. Actualizar desde la versión 1.0.0 conservando datos

1. Detenga el servidor de la versión anterior (`Ctrl+C`).
2. Copie la carpeta `data` (base de datos y archivos) y el archivo `.env` de la carpeta anterior a la carpeta de la v1.0.1.
3. Ejecute `INSTALAR.bat` (o los pasos 3, 4 y 6). `migrate` actualiza la base sin borrar datos; responda **N** a crear usuario y a datos demo.
4. Recomendado antes de copiar: `.venv\Scripts\python.exe manage.py gpv_backup` en la versión anterior.

## 11. Procesos adicionales (opcionales en local)

| Proceso | Comando | Necesario cuando |
|---|---|---|
| Trabajador | `.venv\Scripts\python.exe manage.py run_worker` | `GPV_JOBS_MODE=worker` en `.env` |
| Planificador | `.venv\Scripts\python.exe manage.py run_scheduler` | Usa reportes programados |

Cada uno en su propia terminal; se detienen con `Ctrl+C` y se reanudan con el mismo comando.
En modo `inline` (por defecto local) los trabajos se ejecutan dentro de la solicitud: la página
espera a que terminen y no se pueden cancelar a mitad de un paso largo.

## 12. Pruebas y diagnóstico

```bat
.venv\Scripts\python.exe manage.py test
.venv\Scripts\python.exe manage.py gpv_diagnose
```

## 13. Respaldo y restauración

```bat
.venv\Scripts\python.exe manage.py gpv_backup
.venv\Scripts\python.exe manage.py gpv_restore data\backups\gpv_backup_AAAAMMDD_HHMMSS.zip --confirmar
```

Detalles en `DIAGNOSTICO.md`.

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Cannot find path` / `No such file or directory: 'requirements.txt'` / `can't open file … manage.py` | La terminal está en la carpeta exterior (doble carpeta al extraer) o se copió `<usuario>` literal | Vaya a la carpeta que contiene `manage.py` (sección 1). Si ya creó `.venv` en la carpeta exterior, puede borrarlo |
| `'py' no se reconoce…` | Python no instalado o no está en PATH | Use `python`; si tampoco existe, solicite Python 3.11–3.13 a TI |
| «Acceso denegado» al ejecutar `.venv\Scripts\python.exe` | Política corporativa bloquea ejecutables en el perfil | Solicite a TI una carpeta autorizada (ej. `C:\Apps\GPV`) o un entorno aprobado; no eluda la política |
| `pip` no descarga (proxy) | Proxy corporativo | `.venv\Scripts\python.exe -m pip install --proxy http://usuario@proxy:puerto -r requirements.txt` (solicite datos a TI) |
| Sin Internet | Instalación offline | En un equipo con Internet y la **misma versión de Python**: `py -m pip download -r requirements.txt -d wheels --only-binary=:all: --platform win_amd64 --python-version 3.12`; copie `wheels` y ejecute `.venv\Scripts\python.exe -m pip install --no-index --find-links wheels -r requirements.txt` |
| `Error: That port is already in use.` | Puerto 8000 ocupado | Use otro: `manage.py runserver 127.0.0.1:8010` y abra `http://127.0.0.1:8010/` |
| La página se ve sin estilos | Abrió un HTML directo o `GPV_DEBUG=false` con runserver | Abra la URL del servidor; en local deje `GPV_DEBUG` sin definir (dev). En despliegue ejecute `collectstatic` (ver DESPLIEGUE_INTERNO.md) |
| `DisallowedHost` | Accede con un nombre no permitido | Agregue el nombre a `GPV_ALLOWED_HOSTS` en `.env` |
| «No tiene permiso…» | Rol o área sin permiso | Administración › Usuarios / Permisos por rol |
| «Formato .xls no soportado» | Archivo antiguo o con macros | Guárdelo como .xlsx o .csv desde Excel |
| Reporte «sin datos» | Filtros sin coincidencias o sin importaciones | Revise filtros/periodo y Cargar información › Historial |
| «Requiere LibreOffice…» | Motor Office ausente | Opcional: TI instala LibreOffice y configura `GPV_SOFFICE_PATH`; las herramientas PDF nativas siguen funcionando |
| Impresora «Fallido: no se pudo conectar» | Red, puerto o equipo apagado | Administración › Impresoras › Probar conexión; revise IP/puerto con TI |
| `database is locked` | SQLite con varios usuarios intensivos | Use PostgreSQL para uso compartido |
| Errores de migración | Base de otra versión | `manage.py migrate`; si persiste, restaure un respaldo |
