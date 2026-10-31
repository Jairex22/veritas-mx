# Seguridad y auditoría

## Autenticación y sesiones

* **DEMO:** usuarios sin contraseña, sólo si `GPV_MODE=DEMO`; marcados como DEMO en toda la interfaz.
* **Corporativa:** Autenticación Integrada de Windows delegada a IIS; identidad aceptada sólo desde IPs de proxy
  configuradas; rol asignado únicamente por `config/user_roles.json`. OIDC/Entra ID: fase 2.
* Sesión server-side: token aleatorio de 256 bits en cookie `HttpOnly`, `SameSite=Strict`, `Secure` (configurable);
  en la BD sólo se guarda su hash SHA-256. Expiración configurable (`GPV_SESSION_TTL_MIN`), revocación en logout.
* **CSRF:** token por sesión requerido en `X-CSRF-Token` para todo método no seguro (POST/PUT/PATCH/DELETE).

## Roles y permisos

| Permiso | Operador | Ingeniería | Calidad | Admin |
|---------|:-------:|:---------:|:------:|:----:|
| Trazabilidad, diagnóstico, métricas, catálogo de operaciones | ✔ | ✔ | ✔ | ✔ |
| Packing | ✔ |  | ✔ | ✔ |
| Imprimir etiquetas | ✔ |  | ✔ | ✔ |
| Reimprimir etiquetas (con justificación) |  |  | ✔ | ✔ |
| Auditoría, ver conectores |  | ✔ | ✔ | ✔ |
| Consulta directa OData (credenciales por sesión, en memoria) |  | ✔ | ✔ | ✔ |
| Probar conectores |  | ✔ |  | ✔ |
| Reiniciar DEMO |  |  |  | ✔ |

Cada acción del Centro de Operaciones declara además sus roles (ver `docs/INTEGRATIONS.md`).

## Controles de operaciones

Usuario autenticado · rol autorizado · verificación del estado previo · validación del flujo de proceso ·
token de confirmación HMAC-SHA256 (atado a usuario, acción, parámetros, versión de estado y modo; expira en 180 s) ·
confirmación explícita (`confirm=true` + casilla en la UI) · **idempotencia** por clave única (doble clic o
reintento devuelve la misma respuesta sin repetir la acción) · **control de concurrencia** (409 si el estado
cambió) · comprobación posterior del estado · registro de auditoría con estado previo/posterior.

Prohibido por diseño: escritura directa en tablas de FactoryLogix, Change Product, manipulación de estados.
Acciones destructivas deshabilitadas en todos los modos. DEMO nunca alcanza producción (pruebas
`tests/test_demo_isolation.py`).

## Validación de entrada y salida

* Pydantic + expresiones regulares en rutas y parámetros; parámetros desconocidos rechazados.
* Plantillas ZPL: los valores se escapan (`^`, `~`) para impedir inyección de comandos de impresora.
* Frontend: todo contenido dinámico se inserta como texto (sin `innerHTML`).
* Cabeceras: CSP `default-src 'self'` (sin scripts en línea ni orígenes externos), `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` en la API.
* Errores controlados con código, mensaje, diagnóstico e ID de correlación; sin trazas internas al cliente.

## Credenciales

Sólo en variables de entorno / `.env` del servidor (excluido de git). Nunca en el frontend, JavaScript ni
repositorio. La UI muestra el **origen** de la credencial, nunca su valor. Los logs enmascaran claves sensibles.
TLS verificado por defecto; soporte para CA corporativa (`GPV_CA_BUNDLE`). No se ofrece opción para desactivar
la verificación desde la UI.

## Auditoría

* `audit_log`: autenticación (éxito/denegado), preparación y ejecución de operaciones, impresiones y
  reimpresiones, pruebas de conectores, arranque del sistema y reinicios DEMO.
* Cada registro incluye hash SHA-256 encadenado al anterior; `GET /api/audit` verifica la cadena completa y la
  UI alerta si se rompe.
* `access_log`: cada petición a `/api/*` con usuario, método, ruta, estado HTTP, duración, IP y correlación.
* Datos mínimos: no se almacenan contraseñas ni contenido de FactoryLogix en la BD propia, salvo los parámetros
  y resúmenes de estado de las operaciones auditadas.
