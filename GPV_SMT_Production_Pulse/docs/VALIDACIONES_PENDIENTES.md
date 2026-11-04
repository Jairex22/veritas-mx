# Validaciones pendientes y requisitos que dependen del esquema real

**No se ha probado nada contra el servidor real.** El entorno de desarrollo no tiene acceso a
`http://10.62.54.10:6065/odata/` (desde allí la conexión agota el tiempo de espera). Toda la
funcionalidad se verificó con un servidor OData simulado y datos ficticios. Los nombres de campos
del modo DEMO (`IntervalStart`, `GoodCount`, `LineName`, `WorkOrder`…) **son inventados para la
simulación** y no se asumen en el código: en modo real se usan los campos que declare `$metadata`.

## HTTP 401 en ProductivityOverTime (autenticación de Windows)

Resultado observado en la PC de GPV (04/11/2026):

* `GET $metadata` → **200** sin credenciales (campos identificados).
* `GET ProductivityOverTime?$top=1` → **401** con `WWW-Authenticate: Basic` (la entidad exige
  **usuario y contraseña**, no autenticación de Windows).

Desde la v1.1.4 la aplicación se autentica con la **sesión de Windows del propio operador** (SSPI, sin
instalar nada, sin contraseñas). Dos desenlaces posibles en la PC de planta:

1. **La cuenta del operador tiene permiso de lectura** sobre la entidad → la recolección funciona sin
   intervención de TI. Es el caso esperado si ese usuario ya puede ver la productividad en FactoryLogix.
2. **La cuenta no tiene permiso** → el servidor responde 401/403 incluso autenticado. Esto **no** se puede
   resolver desde la aplicación: TI (o el administrador de FactoryLogix) debe conceder lectura de
   `ProductivityOverTime` a esa cuenta o al grupo de SMT. No se requiere "lectura anónima".

Cómo saber en cuál caso estás: inicia `py app.py --live` y observa el Monitor / *Estado de conexión*:
el aviso indica si "se autenticó con tu sesión de Windows y el servidor la rechazó" (caso 2) o si la
recolección avanzó (caso 1). El log `logs\production_pulse.log` muestra `auth: Windows integrated via SSPI`.

Si la cuenta de la sesión de Windows no es la autorizada, usa *Estado de conexión → Credenciales de
FactoryLogix* para entrar con otra cuenta de Windows (contraseña solo en memoria).

> Validación pendiente en Windows: la capa SSPI (ctypes/Secur32) se probó en la PC de planta en v1.1.4
> (generó el token como el usuario conectado; se corrigió en v1.1.4 un error de declaración ctypes en
> `FreeContextBuffer`). Confirmar en planta que el handshake completo entrega datos, con la sesión actual
> o con credenciales explícitas.

## Requisitos que dependen de lo que exista