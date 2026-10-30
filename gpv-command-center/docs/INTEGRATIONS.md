# D. Integraciones verificadas y pendientes

> **Nota de investigación.** Durante el desarrollo se intentó consultar la documentación oficial
> (`https://xtendapi.aiscorp.com/` y `https://docs.aiscorp.com/en/factorylogix-learning/FL/op/get-started-with-the-xtend-api`).
> Ambos dominios fueron **bloqueados por el proxy de red del entorno de desarrollo**, por lo que **no se verificó
> ningún método, servicio ni endpoint de FactoryLogix**. En consecuencia, el código no contiene nombres de
> servicios xTend, rutas de FactoryLogixAPI ni nombres de entidades OData: todos se configuran tras validarlos
> en la instalación de GPV.

## Estado

| Integración | Estado v1.0 | Detalle |
|-------------|-------------|---------|
| Generador DEMO | ✅ Implementado | Datos sintéticos deterministas, prefijo `DEMO`. Sólo en `GPV_MODE=DEMO`. |
| OData – prueba de conexión | ✅ Implementado y probado (con servidor simulado) | `GET <base>/$metadata`. Diagnóstico de 401 (incluye esquemas `WWW-Authenticate`), 403, 404, 5xx, TLS, timeout. Sin reintentos con credenciales alternativas. Descubre EntitySets. |
| OData – lectura de trazabilidad | ⚠️ Implementado, **no probado contra FactoryLogix real** | Requiere `config/odata_mapping.json` con `verified: true`. Sólo `GET` con `$select`, `$filter`, `$top`. |
| OData – auth Windows (NTLM/Negotiate) | ⏳ Pendiente | Requiere aprobación de TI y una librería adicional (p. ej. `httpx-ntlm`/SSPI). Se detecta y se informa en el diagnóstico. |
| xTend API – transacciones | ⏳ Pendiente de verificación | Sólo prueba de alcance de la URL base. Ninguna acción usa xTend. |
| FactoryLogixAPI | ⏳ Pendiente de verificación | Sólo prueba de alcance. Inventario en `config/flx_endpoints.example.json`. |
| Archivos auxiliares CSV | ✅ Implementado | `events.csv` (+ `defects.csv`) en `GPV_AUX_DIR`. Sólo lectura. |
| Archivos XML de diagnóstico | 🟡 Parcial | Se listan; parser pendiente del formato real de GPV. |
| Microsoft SQL Server (FactoryLogix) | ⛔ Excluido por diseño | No se escribe en tablas de FactoryLogix. Lectura directa sólo si TI lo autoriza (fase 2, vistas de sólo lectura). |
| Impresoras Zebra/CAB | 🟡 Parcial | Comprobación de puerto TCP 9100 sin enviar datos. Impresión real deshabilitada en v1.0. |
| BarTender | ⏳ Pendiente | Requiere Integration Builder / REST API aprobado. Plantilla visible como NO DISPONIBLE. |
| SSO corporativo | ⏳ Pendiente | OIDC / Entra ID, LDAP/AD o Windows Integrated Auth vía IIS. |

## Acciones del Centro de Operaciones

Todas en estado **PENDIENTE** de verificación. En DEMO se simulan; en REAL responden `501 NO DISPONIBLE`.

| Acción | Rol | Validaciones de flujo | Reversión |
|--------|-----|-----------------------|-----------|
| Registrar evento de producción | Operador, Ingeniería, Admin | Unidad activa | Nota correctiva |
| Registrar resultado de prueba | Operador, Ingeniería, Admin | Sin HOLD, sin defectos abiertos, estación de prueba = estación actual | No reversible |
| Registrar defecto | Operador, Calidad, Ingeniería, Admin | Sin HOLD, estación actual | Reparación + re-prueba |
| Registrar reparación | Operador, Ingeniería, Admin | Unidad en reparación, defecto abierto del serial | No reversible; defecto queda REPARADO hasta re-prueba PASS |
| Aplicar HOLD | Calidad, Admin | Unidad activa, sin HOLD | Liberar HOLD |
| Liberar HOLD | Calidad, Admin | En HOLD, sin defectos abiertos, todos los defectos VERIFICADOS | Nuevo HOLD |
| Completar estación (tracking) | Operador, Ingeniería, Admin | Estación no-prueba = estación actual, sin HOLD ni defectos | No reversible |
| Procesar packing | Operador, Calidad, Admin | Caja abierta, capacidad, sin duplicados, ensamble/revisión, unidad liberada en PACK | Desempaque oficial (no implementado) |
| Scrap | Calidad, Admin | — | **Deshabilitada (destructiva)** |

## Procedimiento para habilitar una acción real (fase 2)

Para cada acción, documentar y obtener evidencia de:

1. Método oficial (servicio/operación xTend o endpoint) en la documentación vigente para la versión instalada.
2. Endpoint/servicio concreto en la instalación de GPV.
3. Requisito de licencia confirmado con AEGIS/GPV.
4. Mecanismo de autenticación y cuenta de servicio con privilegios mínimos.
5. Parámetros, validaciones del servidor y códigos de error.
6. Privilegios de FactoryLogix requeridos.
7. Consecuencias y posibilidad de reversión.
8. Pruebas en ambiente de validación con evidencia.
9. Autorización explícita y firmada del responsable de FactoryLogix.

Después: implementar un ejecutor en un módulo nuevo (p. ej. `backend/app/connectors/xtend_actions.py`),
registrarlo en `OperationsService.real_executors`, agregar pruebas con transporte simulado, y activar
`GPV_ALLOW_PRODUCTION_WRITES=true` sólo en el servidor autorizado. Nunca usar Change Product,
modificación de base de datos ni manipulación de estados para eludir controles de proceso.

## Configurar la lectura OData

1. En el servidor, definir `GPV_ODATA_BASE_URL`, `GPV_ODATA_AUTH` y credenciales (variables de entorno).
2. En **Conectores → FactoryLogix OData → Probar conexión**. Si responde 401/403, seguir el diagnóstico
   con el administrador; no intentar otras credenciales.
3. Con estado OK, revisar *EntitySets descubiertos* y, con el responsable del sistema, identificar el conjunto
   de historial de operaciones y sus propiedades.
4. Copiar `config/odata_mapping.example.json` a `config/odata_mapping.json`, completar los nombres exactos,
   `verified: true`, `verified_by`, `verified_on`.
5. `GPV_MODE=REAL`, `GPV_REAL_DATA_SOURCE=odata` y reiniciar el servicio.
