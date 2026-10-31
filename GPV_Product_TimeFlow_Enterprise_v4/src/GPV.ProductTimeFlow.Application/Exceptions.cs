namespace GPV.ProductTimeFlow.Application;

/// <summary>Error de regla de negocio o validación (HTTP 422).</summary>
public class BusinessRuleException : Exception
{
    public IReadOnlyList<string> Errors { get; }
    public BusinessRuleException(string message) : base(message) => Errors = [message];
    public BusinessRuleException(IReadOnlyList<string> errors) : base(errors.Count == 1 ? errors[0] : "La solicitud contiene errores de validación.") => Errors = errors;
}

/// <summary>
/// Recurso inexistente o sin permiso. Se responde igual (HTTP 404) en ambos casos para no revelar la existencia
/// de solicitudes de otros empleados (prevención de IDOR/enumeración).
/// </summary>
public sealed class NotFoundException(string message = "El recurso no existe o no tiene permisos para consultarlo.") : Exception(message);

/// <summary>Acción no permitida sobre un recurso que sí puede consultar (HTTP 403).</summary>
public sealed class ForbiddenException(string message = "No tiene permisos para realizar esta acción.") : Exception(message);

/// <summary>Conflicto de concurrencia o estado (HTTP 409).</summary>
public sealed class ConflictException(string message) : Exception(message);
