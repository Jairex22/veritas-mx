# Manual de instalación — GPV SMT Production Pulse v1.0.0

Requisitos: Windows 11, Python 3.11 o superior (probado con 3.14), cuenta estándar sin
privilegios de administrador. No se usan instaladores MSI, `.bat`, `.exe`, PowerShell, Node.js
ni Docker. La aplicación no necesita bibliotecas externas.

## 1. Descomprimir el ZIP

Clic derecho sobre `GPV_SMT_Production_Pulse_v1.0.0.zip` → **Extraer todo…** → elegir una carpeta
del usuario, por ejemplo `C:\Users\<usuario>\Apps\`. Se crea la carpeta `GPV_SMT_Production_Pulse`.

> Evita carpetas sincronizadas (OneDrive) para la carpeta `data\`: SQLite funciona mejor en disco local.

## 2. Abrir la carpeta

En Visual Studio Code: **Archivo → Abrir carpeta…** → `GPV_SMT_Production_Pulse`.
Abre una terminal con **Terminal → Nueva terminal** (se abre en la carpeta del proyecto).

## 3. Verificar Python

```bat
py --version
```

Debe mostrar `Python 3.11` o superior (por ejemplo `Python 3.14.7`). Si `py` no existe, prueba
`python --version`. Si no hay Python, solicita a TI la instalación por usuario desde python.org
("Install for me only", no requiere administrador).

## 4. Instalar dependencias (solo si hace falta)

**No hay dependencias obligatorias.** Únicamente en estos casos opcionales:

| Caso | Comando (por usuario, sin administrador) |
|---|---|
| TI aprueba autenticación Windows integrada | `py -m pip install --user -r requirements-windows-auth.txt` |
| Se configura `analytics.plant_timezone` con nombre IANA | `py -m pip install --user tzdata` |

Una vez instaladas, funcionan sin conexión a internet. Si pip requiere proxy, TI debe indicarlo;
no desactives controles de seguridad corporativos.

## 5. Ejecutar la aplicación

```bat
py app.py
```

Por defecto `config.json` inicia en modo DEMO. Opciones:

```bat
py app.py --demo          :: forzar modo demostración
py app.py --live          :: usar FactoryLogix
py app.py --port 8780     :: otro puerto si 8765 está ocupado
py app.py --open          :: abrir el navegador automáticamente
```

Detener: `Ctrl + C` en la terminal.

## 6. Abrir en el navegador

**http://127.0.0.1:8765** (Edge o Chrome). La aplicación solo escucha en `127.0.0.1`: no es
accesible desde otras computadoras. Exponerla en red requiere autorización de TI, cambiar
`app.host` y `app.allow_non_localhost`, y controles adicionales (no incluidos en v1.0).

## 7. Activar el modo DEMO

`py app.py --demo` o en `config.json`: `"app": {"mode": "demo"}`. Se muestra la franja
**MODO DEMOSTRACIÓN** en todas las pantallas y reportes. Los datos simulados se guardan en
`data\production_pulse_demo.db`, separado de los datos reales (`data\production_pulse.db`).

## 8. Configurar la conexión OData autorizada

Editar `config.json`, sección `odata`:

```json
"odata": {
  "base_url": "http://10.62.54.10:6065/odata/",
  "entity_set": "ProductivityOverTime",
  "auth_mode": "none",
  "use_system_proxy": false,
  "accept_header": "application/json",
  "append_format_json": false
}
```

* `auth_mode`: `"none"` (acceso anónimo o por red) o `"windows_negotiate"` (usa la sesión
  Windows del usuario; requiere el paso 4). **Nunca** se escriben usuarios ni contraseñas en
  `config.json`; la URL no admite credenciales.
* `use_system_proxy`: `false` para servidores internos (evita enviar tráfico interno al proxy).
* `append_format_json`: solo si el servidor ignora `Accept: application/json` y responde XML.
* `entity_set` solo acepta `ProductivityOverTime`.

Los límites (`limits`) ya están en valores conservadores: `MAX_RECORDS=50`,
`CACHE_TTL_SECONDS=300`, `REQUEST_TIMEOUT_SECONDS=15`, `MAX_CONCURRENT_REQUESTS=1`,
`MIN_REFRESH_INTERVAL_SECONDS=60`, `AUTO_REFRESH_ENABLED=false`. Son límites iniciales de
seguridad, no garantías de rendimiento del servidor.

## 9. Validar la metadata

Con la aplicación en modo `--live`, abrir **Estado de conexión**:

1. **Verificar conexión** → 1 solicitud GET a `$metadata`. Se guarda copia en `data\metadata\`.
2. Revisar **Propiedades detectadas** (campos reales del servidor).
3. **Mapeo de campos**: elegir qué propiedad es fecha/hora, cantidad producida, línea, estación y
   turno. Las sugerencias son solo por nombre; confirmar con el equipo MES. Funciones sin campo
   quedan como **NO DISPONIBLE**. Presionar **Confirmar mapeo**.
4. **Probar compatibilidad** → máximo 7 GET con `$top=1` (límite de registros, `$select`,
   `$orderby`, filtro por fecha, línea, estación, turno).

Alternativa por línea de comandos (sin iniciar el servidor web):

```bat
py metadata_inspector.py --remote --save
```

## 10. Iniciar las primeras consultas reales

En **Producción**: elegir un periodo corto (un día), presionar **Consultar producción**. Si el
filtro por fecha no fue comprobado, la consulta se **bloquea** con la explicación (nunca se
envía una consulta sin filtros). Revisa en **Estado de conexión → Historial** cada URL enviada.

Registra los resultados en [VALIDACIONES_PENDIENTES.md](VALIDACIONES_PENDIENTES.md).

## Solución de problemas

| Síntoma | Acción |
|---|---|
| "No se pudo abrir el puerto 8765" | `py app.py --port 8780` |
| "Autenticación requerida" (401) | Consultar con TI el mecanismo aprobado; `auth_mode` |
| "Consultas en pausa" | El circuit breaker se abrió tras errores; espera el tiempo indicado |
| Pantalla sin estilos | Recargar con `Ctrl+F5` |
| Revisar errores | `logs\production_pulse.log` (sin credenciales ni encabezados Authorization) |

Ejecutar pruebas: `py -m unittest discover -s tests -v`
