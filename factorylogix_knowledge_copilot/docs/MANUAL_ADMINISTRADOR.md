# Manual de administrador

## 1. Primer arranque y administrador inicial

- Si la base de datos no tiene usuarios, se crea `admin` con **contraseña aleatoria de un solo uso**
  (18 caracteres). No existen credenciales fijas en el código.
- La contraseña se muestra una vez en la consola de `INSTALAR_WINDOWS.bat`/`INICIAR_WINDOWS.bat` y se guarda en
  `data\PRIMER_ACCESO_ADMIN.txt` (carpeta local excluida del ZIP).
- Al iniciar sesión se **exige el cambio**; al cambiarla, el archivo se elimina automáticamente.
- Recomendación: crear cuentas nominales de administrador y no compartir `admin`.

### Recuperación de acceso (procedimiento seguro)

Requiere acceso local al servidor (control de la carpeta de la aplicación):

```bat
cd C:\ruta\factorylogix_knowledge_copilot
.venv\Scripts\python.exe scripts\reset_admin.py admin
```

Solicita la nueva contraseña de forma oculta, aplica la política, desbloquea la cuenta y registra
`user.emergency_reset_admin` en auditoría.

## 2. Usuarios y roles

Página **Usuarios y roles**:

- Crear usuario: genera contraseña temporal aleatoria (mostrarla una vez; entregar por canal seguro).
- Cambiar rol: requiere motivo; queda auditado. No se permite dejar el sistema sin administrador activo.
- Restablecer contraseña, desbloquear, activar/desactivar.
- La matriz RBAC completa está en `docs/MATRIZ_RBAC.md`.

Active Directory: `security/auth.py` define `ActiveDirectoryConfig` (desactivado). La integración requiere
validación de TI (LDAPS, cuenta de servicio, mapeo grupo→rol). La app nunca depende de AD para arrancar.

## 3. Configuración

Página **Configuración** (cada cambio se audita como `settings.change`):

| Pestaña | Parámetros |
|---|---|
| Identidad visual | Nombre, empresa, sitio, soporte, colores (#RRGGBB validados), logo PNG/JPG ≤ 2 MB |
| Parámetros | Sentimiento on/off y retención, relevancia mínima, top-k, segregación de funciones, expiración de sesión, entorno DEMO/PILOT/PRODUCTION |
| LLM local | none / ollama / llamacpp, URL (solo loopback o red privada), modelo |
| Vista de configuración | Configuración efectiva sin secretos (solo nombres de secretos configurados) |

Parámetros de archivo: `config/settings.yaml`. Secretos: `.env` (ver `.env.example`).

## 4. Salud del sistema

Verifica: integridad SQLite, modo léxico (FTS5 o respaldo), índice (fragmentos, vectores, modelo), embeddings,
LLM, OCR, conector OData (estado del circuito), **cadena de auditoría**, disco y tamaño de log. Muestra errores
recientes redactados y el entorno (versiones de Python y paquetes).

## 5. Respaldos

- Botón **Crear respaldo ahora** (Salud del sistema): copia en caliente de SQLite (API de backup) + archivos
  originales en `data\backups\respaldo_AAAAMMDDTHHMMSS.zip`. Se conservan los últimos 14.
- Plan completo y restauración: `docs/PLAN_RESPALDO_RESTAURACION.md`.

## 6. Logs y auditoría

| Registro | Ubicación | Contenido |
|---|---|---|
| Técnico | `logs\app.log` (rotativo 5×5 MB) | Eventos técnicos con redacción de secretos. Sin texto de preguntas ni documentos |
| Auditoría | Tabla `audit_log` | Eventos de seguridad/gobierno con ID, fecha, usuario, rol, acción, objeto, resultado, motivo, correlation ID; append-only (triggers) y cadena SHA-256 |
| Errores | Tabla `system_errors` | Tipo y mensaje redactado con correlation ID |

## 7. Mantenimiento

- **Reindexar** (Training Center → Reindexación) tras cambiar el proveedor de embeddings o actualizar reglas.
- **Evaluación RAG** (Evaluaciones) después de cada cambio de contenido o reglas; reportes en `reports\`.
- **Vigencia**: al arrancar se ejecuta la validación de vigencia; también desde Gobierno.
- **Retención**: Gobierno → Retención lista versiones elegibles; la eliminación es manual y autorizada.

## 8. Paso de DEMO a piloto

Ver `docs/DEMO_PILOTO_PRODUCCION.md`. Mínimo: cambiar entorno a `PILOT`, desactivar usuarios `demo_*`,
desactivar/eliminar documentos `DEMO-*`, cargar documentos reales aprobados y reemplazar `config/eval_set.yaml`.
