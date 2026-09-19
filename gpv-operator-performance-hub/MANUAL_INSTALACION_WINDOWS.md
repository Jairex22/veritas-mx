# Manual de instalación en Windows

Guía paso a paso para instalar y ejecutar **GPV Operator Performance Hub** en
una computadora con Windows 10/11, sin usar PowerShell ni Docker.

## 1. Requisitos previos

| Requisito | Versión mínima | Dónde descargarlo |
|---|---|---|
| Python | 3.11 | https://www.python.org/downloads/windows/ |
| Node.js (incluye npm) | 18 LTS | https://nodejs.org/ |

**Importante al instalar Python:** en el instalador, marca la casilla
**"Add python.exe to PATH"** antes de darle a "Install Now". Si ya lo
instalaste sin marcarla, vuelve a ejecutar el instalador y elige "Modify" →
asegúrate de que "Add to PATH" quede activado.

**Al instalar Node.js:** usa las opciones por defecto del instalador `.msi`.

Para confirmar que ambos quedaron instalados correctamente, abre el **Símbolo
del sistema** (`cmd.exe`, no PowerShell) y ejecuta:

```
python --version
node --version
npm --version
```

Debes ver un número de versión en cada caso (no un error de "no se reconoce
el comando").

## 2. Descargar el proyecto

Copia la carpeta `gpv-operator-performance-hub` completa a tu computadora,
por ejemplo en `C:\GPV\gpv-operator-performance-hub`. Evita rutas con
caracteres especiales o demasiado largas.

## 3. Configurar variables de entorno (opcional para la demo)

La aplicación funciona de inmediato con valores por defecto (datos
simulados, SQLite, sin FactoryLogix). Si quieres personalizar algo:

1. Copia `backend\.env.example` como `backend\.env`.
2. Copia `frontend\.env.example` como `frontend\.env`.
3. Edita los valores según necesites (ver comentarios dentro de cada archivo).

Los scripts `.bat` del paso 4 hacen esta copia automáticamente si no existen.

## 4. Iniciar el backend

1. Ve a la carpeta `gpv-operator-performance-hub`.
2. Haz doble clic en **`start-backend.bat`**.
3. Se abrirá una ventana de consola que:
   - Crea un entorno virtual de Python en `backend\.venv` (sólo la primera vez).
   - Instala las dependencias (`fastapi`, `uvicorn`, etc.).
   - Genera la base de datos `backend\veritas_mx.db` con 90 días de datos
     simulados (sólo la primera vez; tarda unos segundos).
   - Levanta el servidor en `http://localhost:8000`.
4. Deja esta ventana abierta mientras uses la aplicación. Para detener el
   servidor, presiona `Ctrl+C` en esa ventana.

Si ves un error de "No se pudo crear el entorno virtual", confirma que
`python --version` funciona en `cmd.exe` como se explicó en el paso 1.

## 5. Iniciar el frontend

1. **Sin cerrar** la ventana del backend, abre otra ventana (doble clic de
   nuevo sobre la carpeta del proyecto).
2. Haz doble clic en **`start-frontend.bat`**.
3. La primera vez instalará las dependencias de Node (puede tardar 1-3
   minutos). Después levantará la interfaz en `http://localhost:5173`.
4. Abre tu navegador (Chrome, Edge o Firefox) en `http://localhost:5173`.

## 6. Iniciar sesión

Usa cualquiera de las cuentas de demostración listadas en `README.md`
(sección 4), por ejemplo:

- Usuario: `admin`
- Contraseña: `Admin#2026`

## 7. Detener la aplicación

Cierra ambas ventanas de consola (o presiona `Ctrl+C` en cada una y confirma
con `S`/`Y` si se pregunta).

## 8. Volver a iniciar más adelante

Simplemente vuelve a ejecutar `start-backend.bat` y `start-frontend.bat`. No
es necesario reinstalar nada: los scripts detectan que el entorno virtual y
`node_modules` ya existen y arrancan directamente. Los datos simulados
persisten en `backend\veritas_mx.db` entre sesiones (si quieres datos nuevos,
borra ese archivo y reinicia el backend).

## 9. Solución de problemas comunes

| Síntoma | Causa probable | Solución |
|---|---|---|
| "python no se reconoce como un comando" | Python no está en el PATH | Reinstala Python marcando "Add to PATH" |
| "npm no se reconoce como un comando" | Node.js no instalado o no en el PATH | Reinstala Node.js con el instalador oficial |
| El frontend carga pero no muestra datos | El backend no está corriendo o CORS mal configurado | Verifica que `start-backend.bat` siga abierto y que `backend\.env` tenga `CORS_ORIGINS=http://localhost:5173` |
| "No fue posible comunicarse con el servidor" en el login | El backend no está corriendo o está en otro puerto | Revisa `frontend\.env` → `VITE_API_BASE_URL` debe apuntar a `http://localhost:8000` |
| Puerto 8000 o 5173 ocupado | Otra aplicación usa ese puerto | Cierra la otra aplicación, o cambia el puerto en el comando `uvicorn` (`start-backend.bat`) / en `vite.config.ts` |

## 10. Generar el build de producción (opcional)

Ver la sección 10 de `README.md` o ejecutar `build-frontend.bat`.
