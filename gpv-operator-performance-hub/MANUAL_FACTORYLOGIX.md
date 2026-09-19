# Manual para conectar FactoryLogix Analytics

Este documento explica cómo activar el conector real hacia **FactoryLogix
Operations/Analytics**. La aplicación funciona completamente sin este paso,
usando datos simulados — actívalo únicamente cuando tengas autorización y
credenciales de tu equipo de IT/MES.

> **No se inventan endpoints reales de FactoryLogix en este proyecto.** El
> conector es una capa de transporte configurable (cliente OData genérico +
> capa de normalización). Debes indicarle la URL base y, si tu instalación
> expone los campos con otros nombres, ajustar el mapeo — ver sección 4.

## 1. Qué necesitas antes de empezar

Solicita a tu equipo de IT/MES / al administrador de FactoryLogix:

1. **URL base del servicio OData** de FactoryLogix Analytics (por ejemplo,
   algo con forma `https://<servidor>/AnalyticsOData` — la URL exacta depende
   de tu instalación).
2. **Usuario y contraseña** con permiso de sólo lectura sobre las entidades
   necesarias (autenticación Basic).
3. Confirmación de **qué entidades** están expuestas y **cómo se llaman los
   campos** relevantes (número de operador, estación, producto, cantidades,
   fechas, etc.), para poder ajustar el mapeo si difiere del esperado.

## 2. Dónde se configuran las credenciales

**Únicamente en el backend**, en el archivo `backend/.env` (nunca en el
frontend, nunca en el código fuente, nunca en un repositorio compartido):

```
FACTORYLOGIX_ENABLED=true
FACTORYLOGIX_BASE_URL=https://tu-servidor/AnalyticsOData
FACTORYLOGIX_USERNAME=usuario_autorizado
FACTORYLOGIX_PASSWORD=contraseña_autorizada
FACTORYLOGIX_TIMEOUT_SECONDS=15
FACTORYLOGIX_MAX_RETRIES=2
```

El frontend nunca ve estas credenciales: sólo consulta el backend, y el
backend es el único que habla con FactoryLogix.

## 3. Nombres de entidad OData configurables

Si tu instalación de FactoryLogix expone las entidades con nombres distintos
a los valores por defecto, ajústalos también en `backend/.env`:

```
FLX_ENTITY_PRODUCTION_ACTIVITY=ProductionActivity
FLX_ENTITY_UNIT_HISTORY=UnitHistory
FLX_ENTITY_WIP=WIP
FLX_ENTITY_ACTIVE_TRACKING=ActiveProductTracking
FLX_ENTITY_ACTIVE_TRACKING_DETAIL=ActiveProductTrackingDetail
FLX_ENTITY_QUALITY=Quality
FLX_ENTITY_FAULTS=Faults
FLX_ENTITY_VALIDATION_EXCEPTIONS=ValidationExceptions
FLX_ENTITY_NON_CONFORMANCE=NonConformance
FLX_ENTITY_USER_CERTIFICATION=UserCertification
FLX_ENTITY_TEST_MEASUREMENT=TestAndMeasurement
FLX_ENTITY_WORK_ORDERS=WorkOrders
FLX_ENTITY_STATIONS=Stations
FLX_ENTITY_PRODUCTS=Products
FLX_ENTITY_USERS=Users
```

## 4. Capa de normalización (mapeo de campos)

El archivo `backend/app/integrations/factorylogix/adapter.py` contiene
funciones `normalize_*` que traducen los registros crudos de OData al modelo
interno de la aplicación. Cada función busca varios nombres de campo
candidatos (por ejemplo `OperatorNumber`, `EmployeeNumber` o `UserID` para el
número de operador) para tolerar variaciones comunes entre instalaciones.

**Si tu instalación usa nombres de campo distintos**, agrega el nombre real
a la lista de candidatos en la función correspondiente. Por ejemplo, en
`normalize_production_activity`:

```python
op_number = _get_first(r, "OperatorNumber", "EmployeeNumber", "UserID")
```

Si tu campo se llama `BadgeID`, simplemente añádelo:

```python
op_number = _get_first(r, "OperatorNumber", "EmployeeNumber", "UserID", "BadgeID")
```

No es necesario tocar ningún otro archivo del sistema: el resto de la
aplicación (routers, motor de puntaje, frontend) trabaja siempre sobre el
modelo interno normalizado.

## 5. Clasificación de causas de defecto

Por diseño, **el adaptador nunca atribuye automáticamente un defecto al
operador**. Los registros de calidad que vienen de FactoryLogix entran con
causa `"Causa sin confirmar"` hasta que ingeniería de calidad la clasifique
(proceso, material, equipo, programa, diseño, método o posible error
operativo). Esto evita decisiones automáticas injustas basadas en datos
crudos sin revisar.

## 6. Comportamiento ante fallas de conexión (modo offline)

El cliente (`backend/app/integrations/factorylogix/client.py`):

- Usa el timeout configurado (`FACTORYLOGIX_TIMEOUT_SECONDS`).
- Reintenta hasta `FACTORYLOGIX_MAX_RETRIES` veces con espera creciente.
- Si todos los intentos fallan, lanza `FactoryLogixConnectionError` y **no**
  falla en silencio: el backend registra el error y la barra superior de la
  aplicación muestra el mensaje "No fue posible consultar FactoryLogix. Se
  muestran los últimos datos disponibles." (modo offline con el último
  conjunto de datos válido).

## 7. Probar la conexión

Con el backend corriendo y `FACTORYLOGIX_ENABLED=true`, usa el botón
**"Actualizar datos"** en la barra superior de la aplicación (o llama a
`POST /api/system/sync`). El estado de conexión se refleja de inmediato en
la barra superior y en la pantalla de Configuración.

## 8. Preparación para Active Directory (futuro)

El modelo `User` (`backend/app/models.py`) ya incluye el campo
`external_directory_id`, reservado para mapear cuentas contra un directorio
externo (Active Directory / LDAP) cuando se decida reemplazar la
autenticación local de demostración. Esa integración no está implementada en
esta versión; se documenta aquí para que el siguiente equipo que la
construya sepa dónde engancharla sin rediseñar el modelo de usuarios.
