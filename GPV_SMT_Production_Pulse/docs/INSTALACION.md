# Manual de instalación — GPV SMT Production Pulse v1.1.4

Windows 11 · Python 3.11 o superior (probado con 3.14) · cuenta estándar **sin permisos de
administrador** · sin Docker, npm, instaladores MSI, `.bat`, `.exe` ni PowerShell sin firmar.

Todos los comandos se escriben en una terminal (**Visual Studio Code → Terminal → Nueva terminal**,
o **Terminal** de Windows) abierta en la carpeta que contiene `app.py`. Los comandos `py ...`
funcionan igual en PowerShell y en CMD. Si `py` responde `can't open file ... app.py`, no estás
en la carpeta correcta (paso 1).

## 1. Descomprimir y entrar a la carpeta correcta

Clic derecho sobre el ZIP → **Extraer todo…**. Windows crea una carpeta con el nombre del ZIP y
**dentro** está la carpeta de la aplicación:

```
GPV_SMT_Production_Pulse_v1.1.4\
└── GPV_SMT_Production_Pulse\      ← aquí están app.py y config.json
```

Abre una terminal **en la carpeta que contiene `app.py`**. Ejemplo si extrajiste en Descargas:

PowerShell (terminal predeterminada de Windows 11 y de VS Code):

```powershell
cd "$env:USERPROFILE\Downloads\GPV_SMT_Production_Pulse_v1.1.4\GPV_SMT_Production_Pulse"
```

Símbolo del sistema (CMD):

```bat
cd /d "%USERPROFILE%\Downloads\GPV_SMT_Production_Pulse_v1.1.4\GPV_SMT_Production_Pulse"
```

> `%USERPROFILE%` solo funciona en CMD; en PowerShell se usa `$env:USERPROFILE`.
> Comprueba con `dir app.py` que el archivo está en la carpeta actual.

Recomendado: usa un disco local (no una carpeta sincronizada de OneDrive) para la carpeta `data\`.

## 2. Verificar Python

```bat
py --version
```

Debe mostrar `Python 3.11` o superior (por ejemplo `Python 3.14.7`). Si `py` no existe, usa
`python --version`. Sin Python: instalador de python.org con la opción "Install for me only"
(no requiere administrador).

## 3. Autenticación: usuario y contraseña de FactoryLogix

No hay que instalar nada con `pip`. El servidor de GPV pide **usuario y contraseña** (autenticación
HTTP Basic). Al abrir la aplicación, ve a **Estado de conexión → Credenciales de FactoryLogix**,
escribe tu usuario y contraseña y pulsa *Guardar y reintentar*. La contraseña se guarda **solo en
memoria** (nunca en disco, en `config.json` ni en los registros). `config.json → odata.auth_mode`:

* `"auto"` (predeterminado): envía usuario/contraseña (Basic) cuando los escribes; en Windows, si el
  servidor pide autenticación integrada, también usa tu sesión (SSPI).
* `"none"`: siempre anónimo (sin enviar credenciales).

Si tu sesión de Windows **no** es la cuenta autorizada en FactoryLogix, abre *Estado de conexión →
Credenciales de FactoryLogix* y escribe una cuenta de Windows con permiso (la contraseña queda solo en
memoria). Si tu usuario y contraseña son correctos y esa cuenta puede leer `ProductivityOverTime`, la
recolección comienza (el Monitor pasa a *Lectura correcta*). Si el servidor responde 401 aun con
credenciales, el usuario o la contraseña no son válidos o esa cuenta no tiene acceso; en ese último
caso TI debe conceder lectura. Ver [VALIDACIONES_PENDIENTES.md](VALIDACIONES_PENDIENTES.md).

## 4. Revisar `config.json`

Valores ya configurados para GPV:

```json
"app":   { "mode": "live", "host": "127.0.0.1", "port": 8765 },
"odata": { "base_url": "http://10.62.54.10:6065/odata/", "entity_set": "ProductivityOverTime",
           "auth_mode": "auto", "use_system_proxy": false },
"collector": { "enabled": true, "interval_seconds": 300, "initial_backfill_hours": 8,
               "lookback_minutes": 15, "max_backoff_seconds": 3600, "recent_activity_minutes": 30,
               "quantity_semantics": "auto", "auto_apply_detected_mapping": true }
```

* `interval_seconds` admite valores de 300 a 3600: **nunca menos de 5 minutos**.
* `quantity_semantics`: cuando MES confirme el significado del campo de cantidad, cambia `"auto"`
  por `"interval"` (cantidad por periodo) o `"cumulative"` (contador acumulado).
* `field_mapping`: si MES confirma los nombres de los campos, puedes escribirlos aquí (por ejemplo
  `"line": "NombreRealDelCampo"`) o confirmarlos desde la pantalla **Estado de conexión**.

## 5. Ejecutar con el servidor real (recolector automático)

```bat
py app.py --live
```

Abre **http://127.0.0.1:8765** en Edge o Chrome. El recolector se inicia solo:

1. lee `$metadata` (1 solicitud);
2. identifica los campos y ejecuta las pruebas de compatibilidad (máximo 8 solicitudes `$top=1`, solo
   la primera vez);
3. hace **1 consulta cada 300 s** mientras la ventana de la terminal esté abierta, **aunque no haya
   ningún navegador abierto**.

Detener: `Ctrl + C` en la terminal.

Variantes:

```bat
py app.py --live --port 8780
```

```bat
py app.py --live --no-collector
```

(`--no-collector`: solo interfaz, sin consultas automáticas.)

## 6. Modo DEMO (sin FactoryLogix)

```bat
py app.py --demo
```

Usa un servidor OData simulado y la base separada `data\production_pulse_demo.db`.

## 7. Ejecutar sin ventana y al iniciar sesión (sin administrador)

Para que siga funcionando sin una terminal abierta, usa `pyw` (Python sin consola). Los mensajes
van a `logs\production_pulse.log`. **`pyw` no muestra errores en pantalla**: valida primero con
`py app.py --live` y usa `pyw` solo cuando funcione.

```bat
pyw app.py --live
```

Para iniciarlo automáticamente al iniciar sesión en Windows (solo para tu usuario):

1. Presiona `Win + R`, escribe `shell:startup` y presiona Enter.
2. Clic derecho → **Nuevo → Acceso directo**.
3. Ubicación del elemento (usa la ruta real de la carpeta que contiene `app.py`):
   `pyw.exe "C:\Users\<usuario>\Downloads\GPV_SMT_Production_Pulse_v1.1.4\GPV_SMT_Production_Pulse\app.py" --live`
4. Nombre: `GPV SMT Production Pulse`. Abre las propiedades del acceso directo y en **Iniciar en**
   escribe la misma carpeta (sin `app.py`).

Para detenerlo: **Administrador de tareas → Detalles → pythonw.exe → Finalizar tarea**.

Solo puede existir **un recolector por equipo**: si intentas iniciar una segunda instancia, el
programa lo indica y termina sin consultar FactoryLogix.

## 8. Validación inicial en GPV

1. **Estado de conexión** → revisar las *Propiedades detectadas* (campos reales del servidor).
2. Revisar el *Mapeo de campos*: si muestra "Auto-detectado por nombre", confírmalo con MES y presiona
   **Confirmar mapeo** (corrige los campos si hace falta).
3. Revisar *Compatibilidad de consultas*: "Límite de registros" y "Filtro por rango de fecha" deben
   decir **Comprobado**; si no, la recolección queda **bloqueada** y la pantalla explica el motivo.
4. Registrar los resultados en [VALIDACIONES_PENDIENTES.md](VALIDACIONES_PENDIENTES.md).

Inspección de metadata por línea de comandos (1 solicitud):

```bat
py metadata_inspector.py --remote --save
```

## 9. Pruebas automatizadas

```bat
py -m unittest discover -s tests -v
```

## Solución de problemas

| Síntoma | Acción |
|---|---|
| `can't open file ... app.py` | No estás en la carpeta correcta: entra a la subcarpeta `GPV_SMT_Production_Pulse` (paso 1) |
| `Cannot find path ...%USERPROFILE%...` | Estás en PowerShell: usa `$env:USERPROFILE` o la ruta completa |
| "Ya hay otra instancia…" | Ya se está ejecutando (revisa `pythonw.exe` en el Administrador de tareas) |
| "No se pudo abrir el puerto 8765" | `py app.py --live --port 8780` |
| Error 401 en el monitor | El servidor exige autenticación. Con `auth_mode "auto"` en Windows ya usa tu sesión; si persiste, tu cuenta no tiene permiso sobre la entidad y TI debe concederlo |
| "Recolección bloqueada" | Ver Estado de conexión → motivo (campo de fecha o filtros no comprobados) |
| "Error: reintento programado" | Servidor sin respuesta: se reintenta con espera creciente (máx. 1 h); los datos previos se conservan |
| Registro de eventos | `logs\production_pulse.log` (rotativo; sin credenciales ni encabezados Authorization) |
