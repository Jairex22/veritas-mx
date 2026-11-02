# Despliegue interno (uso compartido)

`runserver` es **solo para desarrollo**. Para que varias personas usen el portal en la red interna,
TI debe preparar un servidor autorizado. Este documento describe la configuración; **no** cambia el
firewall ni publica nada en Internet. Cada paso es una decisión explícita de TI.

## Arquitectura recomendada

```
Navegadores (Edge/Chrome, PC y celular en la red interna)
        │ HTTPS (certificado interno)
        ▼
Proxy inverso (IIS con ARR, o nginx) ── sirve /static/ (opcional)
        │ HTTP local
        ▼
Waitress (WSGI, Windows) o Gunicorn (Linux)  ──►  PostgreSQL 14+
        │
        ├── manage.py run_worker      (1 o más procesos: importaciones, reportes, documentos, impresión)
        └── manage.py run_scheduler   (exactamente 1 proceso activo: reportes programados)
Carpeta de datos GPV_DATA_DIR: archivos privados, respaldos, logs, temporales (fuera del sitio público)
```

## 1. Preparar el servidor

1. Copie la carpeta del proyecto (ej. `D:\GPV\app`) y cree el entorno como en `INSTALACION_WINDOWS.md`.
2. Instale los opcionales necesarios:
   ```bat
   .venv\Scripts\python.exe -m pip install -r requirements-optional.txt
   .venv\Scripts\python.exe -m pip install "psycopg[binary]==3.2.13"
   ```
   (`pywin32` solo si imprimirá a colas de Windows del servidor.)
3. Cree la base PostgreSQL y un usuario con permisos sobre ella (lo hace el DBA).

## 2. Archivo `.env` de producción

```ini
GPV_ENV=prod
GPV_SECRET_KEY=<salida de: manage.py gpv_genkey>
GPV_ALLOWED_HOSTS=gpvhub.intranet.local
GPV_CSRF_TRUSTED_ORIGINS=https://gpvhub.intranet.local
GPV_DATA_DIR=D:\GPV\data
GPV_DB_ENGINE=postgresql
GPV_DB_NAME=gpvhub
GPV_DB_USER=gpvhub
GPV_DB_PASSWORD=<secreto entregado por TI>
GPV_DB_HOST=localhost
GPV_JOBS_MODE=worker
GPV_ALLOW_DEMO=false
GPV_SECURE_COOKIES=true
GPV_BEHIND_TLS_PROXY=true
GPV_SOFFICE_PATH=C:\Program Files\LibreOffice\program\soffice.exe   (opcional)
```

Proteja `.env` con permisos de lectura solo para la cuenta de servicio.

## 3. Inicializar

```bat
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py collectstatic --noinput
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py check --deploy
.venv\Scripts\python.exe manage.py gpv_diagnose
```

## 4. Servidor WSGI

Windows (Waitress):

```bat
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 --threads=8 gpvhub.wsgi:application
```

Linux (Gunicorn, no incluido en los requisitos; instálelo si aplica):
`gunicorn gpvhub.wsgi:application -b 127.0.0.1:8000 -w 4 --timeout 300`.

Los recursos estáticos: con `GPV_SERVE_STATIC=true` (por defecto) Django sirve `STATIC_ROOT`
después de `collectstatic`; para mayor eficiencia, configure el proxy para servir
`<GPV_DATA_DIR>\staticfiles` en `/static/` y ponga `GPV_SERVE_STATIC=false`.
Los archivos de usuarios **nunca** se sirven como estáticos: siempre pasan por la vista con permisos.

## 5. HTTPS

Configure un certificado interno en IIS/nginx y reenvíe a `127.0.0.1:8000` con la cabecera
`X-Forwarded-Proto: https`. Con `GPV_BEHIND_TLS_PROXY=true` Django la reconoce; las cookies de
sesión y CSRF se marcan `Secure`. Active HSTS (`GPV_HSTS_SECONDS`) solo cuando TODO el dominio use HTTPS.

## 6. Procesos persistentes

Registre como servicios (por ejemplo con el Programador de tareas de Windows «Al iniciar el
sistema», o la herramienta de servicios que TI autorice):

| Servicio | Comando | Instancias |
|---|---|---|
| Web | `waitress-serve …` | 1 |
| Trabajador | `.venv\Scripts\python.exe manage.py run_worker` | 1–4 (concurrencia segura: reclamo atómico) |
| Planificador | `.venv\Scripts\python.exe manage.py run_scheduler` | **1** (además usa un *lease* en BD que impide dos activos) |
| Limpieza diaria | `.venv\Scripts\python.exe manage.py cleanup_temp` | Tarea programada diaria |
| Respaldo | `.venv\Scripts\python.exe manage.py gpv_backup` | Tarea programada diaria; copie el ZIP a otro equipo |

**Qué pasa si el servidor estuvo apagado:** al reanudar, el planificador genera **una** vez la
ocurrencia más reciente de cada programación vencida y registra cuántas se omitieron; los trabajos
que estaban «en proceso» sin latido por 15 minutos se reencolan (hasta `GPV_JOB_MAX_ATTEMPTS`) o
se marcan fallidos con mensaje. Detener: `Ctrl+C` o detener el servicio; reanudar: iniciar de nuevo.

## 7. Seguridad y operación

* Contraseñas con hash PBKDF2 de Django; mínimo 10 caracteres; cambio obligatorio al primer acceso de usuarios creados por el administrador.
* CSRF en todos los formularios, CSP sin scripts externos ni en línea, `X-Frame-Options`, `nosniff`.
* Permisos verificados en el servidor por rol y por área para páginas, archivos, datasets, trabajos, reportes y descargas.
* Logs en `GPV_DATA_DIR\logs\gpvhub.log` con ID de operación; no contienen contraseñas ni contenidos de archivos.
* Datos de demostración desactivados (`GPV_ALLOW_DEMO=false`).
* Las impresoras se registran solo por administradores y quedan deshabilitadas hasta probar conexión.
* No se envían correos ni mensajes externos.

## 8. Capacidad

La prueba local (SQLite, 4 vCPU) se documenta en `TEST_RESULTS.md`. **No certifica** capacidad para
cientos de usuarios. Repita `tools/load_test.py` y `manage.py gpv_benchmark` en el servidor real con
PostgreSQL y Waitress antes de comprometer niveles de servicio.

## 9. Integraciones futuras

La primera versión se alimenta de archivos cargados y capturas autorizadas. Para FactoryLogix,
Dynamics u otros sistemas, la capa de importación (`apps/production/importer.py`) admite un
adaptador que entregue filas con el mismo mapeo; no hay credenciales ni endpoints configurados.
