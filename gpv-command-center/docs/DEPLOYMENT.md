# Instalación y despliegue

## Requisitos

* Python 3.10 o superior (probado con 3.13) en el servidor aprobado por TI.
* Tres paquetes de ejecución: `fastapi`, `uvicorn`, `httpx` (más `pytest` para pruebas).
* **No** requiere Docker, Node/npm/npx, compilación del frontend ni acceso a CDN.

## 1. Desarrollo / evaluación (modo DEMO)

```bat
cd gpv-command-center
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements-dev.txt
scripts\run_tests.bat
scripts\run_server.bat
```

Abrir `http://127.0.0.1:8080/`. Los `.bat` se ejecutan con `cmd.exe`; no es necesario modificar la
política de ejecución de PowerShell. En Linux/macOS: `scripts/run_tests.sh` y `scripts/run_dev.sh`.

Documentación interactiva de la API: `http://127.0.0.1:8080/api/docs`.

## 2. Servidor sin acceso a Internet (paquetes offline)

En un equipo autorizado con acceso al repositorio de paquetes:

```bat
scripts\build_offline_wheels.bat
```

Copiar la carpeta `wheels\` al servidor y ejecutar:

```bat
python -m pip install --no-index --find-links wheels -r requirements.txt
```

## 3. Servicio centralizado en Windows Server (recomendado)

1. Copiar el proyecto a una ruta controlada (p. ej. `D:\GPVCommandCenter`), crear el entorno virtual e instalar dependencias.
2. Copiar `.env.example` a `.env` y ajustar. Las credenciales pueden definirse como variables de entorno del
   servicio en lugar de `.env`. Restringir permisos NTFS de `.env`, `config\` y `var\` a la cuenta del servicio.
3. Ejecutar Uvicorn escuchando **sólo en localhost**: `scripts\run_server.bat 127.0.0.1 8080`.
4. Publicar con **IIS** como proxy inverso HTTPS (URL Rewrite + ARR, o HttpPlatformHandler), con el certificado
   corporativo. Definir `GPV_COOKIE_SECURE=true`.
5. Para que el proceso sea un servicio persistente, TI debe elegir el mecanismo aprobado en GPV (servicio de
   Windows gestionado por TI, HttpPlatformHandler de IIS, o Programador de tareas "al iniciar"). La aplicación no
   instala servicios ni cambia políticas por sí misma.

### Inicio de sesión corporativo (IIS + Autenticación de Windows)

1. En el sitio IIS: habilitar *Autenticación de Windows*, deshabilitar *Anónima*.
2. Con URL Rewrite, establecer una variable de servidor que reenvíe la identidad (p. ej. `HTTP_X_REMOTE_USER`
   = `{LOGON_USER}`) y **eliminar** cualquier `X-Remote-User` enviado por el cliente.
3. En `.env`: `GPV_PROXY_AUTH_HEADER=X-Remote-User`, `GPV_PROXY_AUTH_TRUSTED_IPS=127.0.0.1,::1`.
4. Copiar `config\user_roles.example.json` a `config\user_roles.json` y asignar roles (`DOMINIO\usuario`).
   Usuarios no listados no pueden entrar.

> El encabezado sólo se acepta si la conexión proviene de una IP de proxy de confianza. Uvicorn debe escuchar en
> `127.0.0.1` para que nadie pueda enviarle el encabezado directamente.

## 4. Pasar a modo REAL (sólo lectura)

1. `GPV_MODE=REAL` (desactiva automáticamente el login DEMO y los datos sintéticos).
2. Elegir fuente: `GPV_REAL_DATA_SOURCE=odata` (ver `docs/INTEGRATIONS.md`) o `aux` con `GPV_AUX_DIR`.
3. Reiniciar el servicio. En **Conectores**, ejecutar *Probar conexión*. El distintivo **CONECTADO** sólo aparece
   cuando la fuente activa superó la prueba; **SOLO LECTURA** permanece mientras no existan transacciones verificadas.

## 5. Operación

| Elemento | Ubicación | Notas |
|----------|-----------|-------|
| Base de datos propia | `var/gpv_command_center.db` | SQLite (WAL). Respaldar diariamente junto con `var/secret.key`. |
| Logs | `var/logs/app.log` | JSON por línea, rotación 5 × 5 MB, incluye `correlation_id`. |
| Auditoría | Pantalla Auditoría / `GET /api/audit` | Integridad verificable (`integrity.valid`). |
| Salud | `GET /api/health` | Para monitoreo. |

Para correlacionar un error reportado por un usuario, buscar el *ID de correlación* que muestra la UI en
`app.log` y en Auditoría.

## 6. Pruebas automatizadas

```bat
scripts\run_tests.bat
```

66 pruebas: aislamiento DEMO/producción, operaciones (CSRF, roles, confirmación, token, idempotencia,
concurrencia, flujo), diagnóstico, conectores (401/500/timeout/TLS/metadata/mapeo), API, etiquetas,
autenticación corporativa y frontend servido.
