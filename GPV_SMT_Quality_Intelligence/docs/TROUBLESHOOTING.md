# Guía de solución de errores

| Síntoma / estado | Significado | Acción |
|---|---|---|
| Barra naranja "MODO DEMOSTRACIÓN" | `mode = demo` | Normal para pruebas. Para datos reales ver README §3 |
| `BLOCKED_BY_POLICY` "modo real no aprobado" | `security.live_mode_approved = false` | TI/MES debe aprobar y editar `config.json` |
| `BLOCKED_BY_POLICY` "Basic Auth sobre HTTP" | Se intenta enviar contraseña sin cifrar | Usar `https://` (proxy corporativo) o aprobación explícita de TI |
| `NOT_CONFIGURED` | Falta credencial | Definir `GPV_ODATA_USER`/`GPV_ODATA_PASSWORD` o `main.py --set-credential` |
| `AUTH_ERROR` (401) | Credencial rechazada | Verificar usuario/contraseña con MES. **No se reintenta** |
| `FORBIDDEN` (403) | Usuario sin permiso sobre la entidad | Solicitar permiso en FactoryLogix |
| `NOT_FOUND` (404) | Entidad o ruta inexistente | Revisar `base_url` (debe terminar en `/odata/`) y `$metadata` |
| `BAD_REQUEST` (400) | El servidor no acepta el filtro | Copiar diagnóstico y revisar tipos en "Diferencias de tipo" |
| `SERVER_ERROR` (5xx) / `RATE_LIMITED` (429) | Error o saturación del servidor | Se reintenta con backoff; si persiste, contactar MES |
| `TIMEOUT` | Sin respuesta en `timeout_seconds` | Reducir ventana/filtros. No se reintenta para no sobrecargar |
| `CONNECTION_ERROR` | Red, DNS o puerto cerrado | Confirmar estar en la red GPV/VPN; `Test-NetConnection 10.62.54.10 -Port 6065` (si PowerShell lo permite) |
| `INVALID_RESPONSE` | JSON inválido o estructura inesperada (p. ej. página HTML de login) | Revisar proxy/servidor; copiar diagnóstico |
| `BUSY` | Ya hay una consulta en curso (límite 1) | Esperar y reintentar |
| "· caché" en amarillo | Se muestra la última lectura válida | Datos posiblemente desactualizados |
| "Servidor local no disponible" | La consola de `main.py` se cerró | Volver a ejecutar `py -3.14 main.py` |
| Puerto ocupado (`OSError: [WinError 10048]`) | Otro proceso usa 8765 | `py -3.14 main.py --port 8800` |
| `ERROR de configuración: config.json no debe contener contraseñas` | Se escribió una contraseña en el archivo | Eliminarla; usar variables de entorno o Credential Manager |
| La app no abre el navegador | Política de TI | Abrir `http://127.0.0.1:8765/` manualmente |

**Copiar diagnóstico** (Diagnóstico OData) genera un texto sin contraseñas para enviar a MES/TI. Los logs están en `logs/app_YYYY-MM-DD.log` y se sanitizan (Authorization, password, credenciales en URL).
