# Manual de instalación (Windows 11)

## 1. Requisitos

| Requisito | Detalle |
|---|---|
| Sistema | Windows 10/11 x64 |
| Python | 3.10 a 3.13 (recomendado 3.11 o 3.12). Instalación “solo para mí” válida, sin administrador |
| Disco | ~600 MB (entorno virtual + dependencias) + espacio para documentos |
| Red | Opcional. Sin Internet se instala con `wheelhouse\` |
| No requerido | PowerShell, Node.js, npm, Docker, permisos de administrador, servicios de nube |

Compatibilidad verificada: la resolución de dependencias con wheels binarios para `win_amd64` se comprobó para
Python 3.10, 3.11, 3.12, 3.13 y 3.14 (`pip download --platform win_amd64 --only-binary=:all:`). La suite de
pruebas se ejecutó en Linux con Python 3.11 usando tanto las versiones más recientes como las mínimas declaradas.

## 2. Instalación estándar (con acceso a PyPI o proxy corporativo)

1. Copia la carpeta del proyecto a una ruta con permisos de escritura, por ejemplo
   `C:\Users\<usuario>\Apps\factorylogix_knowledge_copilot`.
2. Si usas proxy corporativo, abre `cmd` y ejecuta antes `set HTTPS_PROXY=http://proxy:puerto`.
3. Doble clic en `INSTALAR_WINDOWS.bat`. El script:
   1. Se ubica en su propia carpeta (`cd /d "%~dp0"`).
   2. Detecta `py -3` o `python` y descarta el alias de Microsoft Store.
   3. Valida la versión (`scripts\check_env.py python`).
   4. Crea `.venv` y comprueba que `.venv\Scripts\python.exe` existe.
   5. Instala `requirements.txt` solo si cambió (huella SHA-256), evitando reinstalar en cada inicio.
   6. Inicializa la base de datos, crea el administrador inicial y carga datos DEMO.
   7. Mantiene la ventana abierta si algo falla, con un mensaje comprensible.
4. Guarda la contraseña temporal de `admin` que se muestra.

Reinstalación forzada: `INSTALAR_WINDOWS.bat /force`.

## 3. Instalación sin Internet

1. En un equipo con Internet y **la misma versión de Python**, ejecuta `scripts\PREPARAR_WHEELS_OFFLINE.bat`.
2. Copia la carpeta `wheelhouse\` generada dentro de la carpeta del proyecto en el equipo destino.
3. Ejecuta `INSTALAR_WINDOWS.bat`: detecta `wheelhouse\` y usa `pip --no-index --find-links wheelhouse`.

## 4. Inicio

| Script | Uso |
|---|---|
| `INICIAR_WINDOWS.bat` | Solo este equipo (`127.0.0.1`). Abre el navegador y muestra la URL |
| `INICIAR_RED_INTERNA_WINDOWS.bat` | Red interna (`0.0.0.0`). Muestra las URL de red para estaciones con solo navegador |
| `DETENER_WINDOWS.bat` | Detiene el servidor registrado (`data\server.pid`) usando `taskkill` sobre el propio proceso |

El lanzador busca un puerto libre entre `server.preferred_port` (8501) y `server.port_range_end` (8599).
Si la aplicación ya está en ejecución, solo abre el navegador.

### Acceso desde la red interna

- El firewall de Windows puede preguntar si se permite el acceso: requiere aprobación de TI (puede pedir
  administrador). Alternativa: que TI publique un puerto fijo y una regla de firewall.
- Recomendado para piloto/producción: colocar un proxy inverso interno (IIS/NGINX) con HTTPS y cabeceras de
  seguridad (ver `docs/CHECKLIST_SEGURIDAD.md`).

## 5. Configuración

- `config\settings.yaml`: parámetros no sensibles (marca, puertos, límites, RAG, retención, matriz de acceso).
- `.env` (copiar desde `.env.example`): secretos y overrides (`FLKC_*`). Nunca se distribuye.
- `config\rules.yaml`: glosario bilingüe, patrones de seguridad, léxico de sentimiento.

## 6. Componentes opcionales

| Componente | Cómo habilitar |
|---|---|
| LLM local (Ollama) | Instalar Ollama aprobado por TI, descargar modelo, `FLKC_LLM_PROVIDER=ollama` o desde Configuración → LLM local |
| llama.cpp server | Iniciar `llama-server` local, `FLKC_LLM_PROVIDER=llamacpp`, `FLKC_LLM_BASE_URL=http://127.0.0.1:8080` |
| Embeddings semánticos | `pip install sentence-transformers` (requiere torch), copiar el modelo a `models_local\paraphrase-multilingual-MiniLM-L12-v2`, `FLKC_EMBEDDING_PROVIDER=sentence_transformers`, luego **Reindexar** en Training Center |
| OCR | Instalar Tesseract (con idiomas spa+eng) y `pip install pytesseract` |

La aplicación **abre aunque ninguno esté instalado**; Salud del sistema muestra su estado.

## 7. Solución de problemas

| Síntoma | Acción |
|---|---|
| “No se encontró Python” | Instalar Python (usuario actual) y marcar “Add to PATH”; desactivar alias de Store |
| Falla `pip install` | Revisar proxy (`HTTPS_PROXY`) o usar `wheelhouse\` |
| El navegador no abre | Copiar la URL mostrada en la ventana |
| Puerto ocupado | El lanzador elige otro automáticamente; revisar rango en `settings.yaml` |
| Olvido de contraseña de admin | Ver `docs/MANUAL_ADMINISTRADOR.md` → Recuperación |
| Errores | `logs\app.log` (sin datos sensibles) y Salud del sistema → errores recientes |
