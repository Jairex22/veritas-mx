# Guía para conectar OData de FactoryLogix de forma segura

El conector es **solo lectura**, está **desactivado por defecto** y la aplicación funciona completa sin él.
No existe ningún método para Proceed, Unproceed, Reroute, cierre de defectos ni modificaciones de producción.

## 1. Prerrequisitos (MES + TI)

1. URL interna del servicio OData de FactoryLogix Analytics (por ejemplo
   `https://factorylogix.intranet.local/Analytics/odata`). Validar con el `$metadata` real de su versión.
2. **Cuenta de servicio de solo lectura** con acceso únicamente a las entidades necesarias.
3. Certificado TLS interno confiable en el servidor del asistente.
4. Aprobación de seguridad y del propietario de datos de FactoryLogix.

## 2. Configuración

`.env` (nunca en el código ni en YAML):

```ini
FLKC_ODATA_ENABLED=true
FLKC_ODATA_BASE_URL=https://factorylogix.intranet.local/Analytics/odata
FLKC_ODATA_TOKEN=<token de solo lectura>
# o bien
FLKC_ODATA_USERNAME=<cuenta_servicio>
FLKC_ODATA_PASSWORD=<contraseña>
```

`config/settings.yaml → connectors.odata`:

```yaml
allowed_hosts: [factorylogix.intranet.local]   # obligatorio recomendado
timeout_seconds: 10
max_retries: 2            # solo 429, 5xx, timeout y sin conexión
backoff_seconds: 1.0      # exponencial: 1s, 2s
circuit_failure_threshold: 3
circuit_reset_seconds: 60
cache_ttl_seconds: 120
max_rows: 200
verify_tls: true
```

Sin `allowed_hosts`, el host debe resolver a una IP privada o loopback; de lo contrario se rechaza.

## 3. Entidades

`config/odata_entities.yaml` define, por entidad, `key_fields` (campos por los que se permite filtrar) y
`select` (columnas devueltas). Ejemplos incluidos: AssemblyGenealogy, InstalledComponentRecord,
PartRelationships, Packout, ShippingOrders, ActiveProductTracking, ActiveProductTrackingDetail, WIP, Quality,
Faults, ValidationExceptions, UserCertification, TestAndMeasurement, ProductivityOverTime, WhereFound.
**Los nombres de campos son ilustrativos**: ajustarlos al `$metadata` real. `ProductivityOverTime` debe usarse
solo agregado por línea/periodo, nunca por empleado.

## 4. Controles implementados

| Control | Implementación |
|---|---|
| Solo lectura | Solo `GET`; sin métodos de escritura |
| Feature flag | `connectors.odata.enabled` |
| Validación | Entidad y campo en allowlist; valor validado (letras, números, `. _ - /`) y comillas escapadas |
| Timeout, reintentos, backoff | Configurables; 401/403/404 no se reintentan |
| Circuit breaker | Abre tras N fallos; semiabierto tras el periodo de espera |
| Caché | TTL por consulta |
| Errores | Mensajes distintos para 401, 403, 404, 429, 5xx, timeout y sin conexión |
| Sanitización | Solo columnas de `select`; valores truncados; sin metadatos `@odata` |
| Proxies | `trust_env=False` (no usa proxies del sistema) |
| Auditoría | `connector.odata_query` con resultado y número de filas |
| Permiso | `connectors.query` (Supervisor, Ingeniería, MES, etc.; no Operador por defecto) |

## 5. Presentación al usuario

Los datos en vivo se muestran en una sección separada “Información consultada en FactoryLogix (solo lectura)”,
distinta de la “Información documental” y de la “Inferencia del sistema”.

## 6. Verificación

1. Salud del sistema → Conector OData = OK, circuito `closed`.
2. Evaluaciones → la resiliencia incluye pruebas simuladas de sin conexión, 401, 500 y timeout.
3. Pruebas: `tests/unit/test_connectors.py` (mocks; no requieren FactoryLogix real).
