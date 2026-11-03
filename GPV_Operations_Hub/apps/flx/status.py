"""Connection / entity status vocabulary shown in the FactoryLogix Connection Center."""
CONNECTED = "CONNECTED"
AUTH_REQUIRED = "AUTHENTICATION REQUIRED"
FORBIDDEN = "FORBIDDEN"
NOT_FOUND = "ENDPOINT NOT FOUND"
TIMEOUT = "TIMEOUT"
SERVER_ERROR = "SERVER ERROR"
NO_DATA = "NO DATA"
SCHEMA_MISMATCH = "SCHEMA MISMATCH"
# additional, more specific states (never shown as "connected")
UNREACHABLE = "UNREACHABLE"            # no network route / connection refused / DNS
RATE_LIMITED = "RATE LIMITED"          # HTTP 429
BAD_RESPONSE = "BAD RESPONSE"          # 200 but not a valid OData payload
BAD_REQUEST = "BAD REQUEST"            # HTTP 400 (option not supported, invalid filter...)
CIRCUIT_OPEN = "CIRCUIT OPEN"          # temporarily not querying after repeated failures
CONFIG_ERROR = "CONFIG ERROR"          # missing configuration / dependency
NOT_TESTED = "NOT TESTED"
OK = "OK"                              # a diagnostic stage that is not a data connection (config, auth discovery)

EXPLAIN = {
    CONNECTED: "Respuesta válida recibida y verificada.",
    AUTH_REQUIRED: "El servidor exige autenticación (HTTP 401) o rechazó las credenciales configuradas.",
    FORBIDDEN: "Autenticado, pero sin permiso de lectura para este recurso (HTTP 403).",
    NOT_FOUND: "El recurso no existe en el servicio (HTTP 404).",
    TIMEOUT: "Sin respuesta dentro del tiempo límite configurado.",
    SERVER_ERROR: "El servidor respondió con un error (HTTP 5xx).",
    NO_DATA: "Consulta válida, pero sin registros.",
    SCHEMA_MISMATCH: "La respuesta no coincide con lo declarado en $metadata.",
    UNREACHABLE: "No hay conexión de red con el servidor (¿equipo fuera de la red de GPV?).",
    RATE_LIMITED: "El servidor limitó las solicitudes (HTTP 429).",
    BAD_RESPONSE: "La respuesta no es un documento OData válido (¿página de inicio de sesión o proxy?).",
    BAD_REQUEST: "El servidor rechazó la consulta (HTTP 400): opción u operador no soportado.",
    CIRCUIT_OPEN: "Pausa automática tras fallas repetidas; se reintenta al terminar el periodo de espera.",
    CONFIG_ERROR: "Falta configuración o una dependencia en este equipo.",
    NOT_TESTED: "Aún no se ha probado.",
    OK: "Etapa verificada (no implica conexión a datos).",
}
OK_STATES = {CONNECTED, NO_DATA}
STAGE_OK = OK_STATES | {OK}
TRANSIENT = {TIMEOUT, SERVER_ERROR, UNREACHABLE, RATE_LIMITED}
CSS = {CONNECTED: "tag-ok", NO_DATA: "tag-info", NOT_TESTED: "tag", RATE_LIMITED: "tag-warn", CIRCUIT_OPEN: "tag-warn", SCHEMA_MISMATCH: "tag-warn"}


def css(state):
    return CSS.get(state, "tag-err")
