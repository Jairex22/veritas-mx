namespace Gpv.Sqi.Models;

/// <summary>
/// Estados explícitos de una consulta. Nunca se usa bool: la UI debe poder
/// distinguir "sin registros" de "no se pudo consultar".
/// </summary>
public enum ODataStatus
{
    OK,                 // Respuesta válida con registros
    EMPTY,              // Respuesta válida sin registros (NO equivale a PASS)
    AUTH_ERROR,         // HTTP 401
    FORBIDDEN,          // HTTP 403
    NOT_FOUND,          // HTTP 404
    BAD_REQUEST,        // HTTP 400
    RATE_LIMITED,       // HTTP 429
    SERVER_ERROR,       // HTTP 5xx
    HTTP_ERROR,         // Otro código HTTP
    TIMEOUT,
    CONNECTION_ERROR,   // Red, DNS, conexión rechazada/interrumpida
    INVALID_RESPONSE,   // JSON inválido o estructura inesperada
    BLOCKED_BY_POLICY,  // Modo real no aprobado / Basic sobre HTTP
    NOT_CONFIGURED,     // Faltan credenciales
    VALIDATION_ERROR,   // Entrada rechazada antes de consultar
    BUSY,               // Límite de concurrencia alcanzado
    NOT_REQUESTED,      // La fuente no fue necesaria
}

public static class ODataStatusInfo
{
    public static readonly HashSet<int> RetryableHttp = [429, 500, 502, 503, 504];

    public static bool IsSuccess(this ODataStatus s) => s is ODataStatus.OK or ODataStatus.EMPTY;

    public static string LabelEs(this ODataStatus s) => s switch
    {
        ODataStatus.OK => "Consulta correcta",
        ODataStatus.EMPTY => "Consulta correcta sin registros",
        ODataStatus.AUTH_ERROR => "Autenticación rechazada (HTTP 401)",
        ODataStatus.FORBIDDEN => "Acceso denegado (HTTP 403)",
        ODataStatus.NOT_FOUND => "Entidad o endpoint no encontrado (HTTP 404)",
        ODataStatus.BAD_REQUEST => "Consulta rechazada por el servidor (HTTP 400)",
        ODataStatus.RATE_LIMITED => "Servidor saturado (HTTP 429)",
        ODataStatus.SERVER_ERROR => "Error interno de FactoryLogix (HTTP 5xx)",
        ODataStatus.HTTP_ERROR => "Respuesta HTTP no esperada",
        ODataStatus.TIMEOUT => "Tiempo de espera agotado",
        ODataStatus.CONNECTION_ERROR => "Servidor inaccesible (red/DNS)",
        ODataStatus.INVALID_RESPONSE => "Respuesta OData inválida",
        ODataStatus.BLOCKED_BY_POLICY => "Bloqueado por política de seguridad",
        ODataStatus.NOT_CONFIGURED => "Conexión no configurada",
        ODataStatus.VALIDATION_ERROR => "Entrada no válida",
        ODataStatus.BUSY => "Otra consulta OData en curso",
        ODataStatus.NOT_REQUESTED => "No requerida",
        _ => s.ToString(),
    };
}
