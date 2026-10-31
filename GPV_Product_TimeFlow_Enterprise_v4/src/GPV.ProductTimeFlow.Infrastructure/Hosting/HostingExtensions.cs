using System.Security.Claims;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;

namespace GPV.ProductTimeFlow.Infrastructure.Hosting;

public static class ActorFactory
{
    /// <summary>Construye el actor a partir de los claims emitidos por TimeFlow (cookie o JWT).</summary>
    public static Actor? FromPrincipal(ClaimsPrincipal? user, HttpContext? http = null)
    {
        if (user?.Identity?.IsAuthenticated != true) return null;
        if (!int.TryParse(user.FindFirst(TimeFlowClaims.EmployeeId)?.Value, out var id)) return null;
        var roles = int.TryParse(user.FindFirst(TimeFlowClaims.Roles)?.Value, out var r) ? (UserRole)r : UserRole.None;
        var name = user.FindFirst(ClaimTypes.Name)?.Value ?? user.FindFirst("name")?.Value ?? "Usuario";
        return new Actor(id, name, roles, http?.Connection.RemoteIpAddress?.ToString(), http?.Request.Headers.UserAgent.ToString());
    }

    public static IEnumerable<Claim> Claims(int employeeId, string name, string email, UserRole roles, Guid securityStamp) =>
    [
        new(ClaimTypes.NameIdentifier, employeeId.ToString()),
        new(ClaimTypes.Name, name),
        new(ClaimTypes.Email, email),
        new(TimeFlowClaims.EmployeeId, employeeId.ToString()),
        new(TimeFlowClaims.Roles, ((int)roles).ToString()),
        new(TimeFlowClaims.SecurityStamp, securityStamp.ToString("N")),
        .. Enum.GetValues<UserRole>().Where(x => x != UserRole.None && roles.HasFlag(x)).Select(x => new Claim(ClaimTypes.Role, x.ToString()))
    ];
}

/// <summary>Manejo global de excepciones → ProblemDetails en español. Nunca expone trazas ni detalles internos.</summary>
public sealed class TimeFlowExceptionHandler(ILogger<TimeFlowExceptionHandler> logger) : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(HttpContext http, Exception exception, CancellationToken ct)
    {
        var (status, title, errors) = Map(exception);
        if (status >= 500) logger.LogError(exception, "Error no controlado en {Path}", http.Request.Path);
        else logger.LogInformation("Solicitud rechazada {Status} {Path}: {Message}", status, http.Request.Path, exception.Message);
        var problem = new ProblemDetails { Status = status, Title = title, Detail = status >= 500 ? "Ocurrió un error inesperado. El incidente quedó registrado." : exception.Message, Instance = http.Request.Path };
        if (errors is not null) problem.Extensions["errors"] = errors;
        problem.Extensions["traceId"] = http.TraceIdentifier;
        http.Response.StatusCode = status;
        await http.Response.WriteAsJsonAsync(problem, ct);
        return true;
    }

    public static (int Status, string Title, IReadOnlyList<string>? Errors) Map(Exception ex) => ex switch
    {
        BusinessRuleException b => (StatusCodes.Status422UnprocessableEntity, "Validación", b.Errors),
        InvalidTransitionException or ConflictException => (StatusCodes.Status409Conflict, "Conflicto", null),
        DomainException => (StatusCodes.Status422UnprocessableEntity, "Regla de negocio", null),
        NotFoundException => (StatusCodes.Status404NotFound, "No encontrado", null),
        ForbiddenException => (StatusCodes.Status403Forbidden, "Sin permiso", null),
        BadHttpRequestException => (StatusCodes.Status400BadRequest, "Solicitud inválida", null),
        _ => (StatusCodes.Status500InternalServerError, "Error interno", null)
    };
}

public static class SecurityHeaders
{
    /// <summary>Cabeceras de seguridad (CSP, anti-clickjacking, MIME sniffing, referrer, permisos).</summary>
    public static IApplicationBuilder UseTimeFlowSecurityHeaders(this IApplicationBuilder app, bool allowInlineStyles = true) =>
        app.Use(async (http, next) =>
        {
            var h = http.Response.Headers;
            h["X-Content-Type-Options"] = "nosniff";
            h["X-Frame-Options"] = "DENY";
            h["Referrer-Policy"] = "strict-origin-when-cross-origin";
            h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()";
            h["Cross-Origin-Opener-Policy"] = "same-origin";
            h["Content-Security-Policy"] =
                "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self' https://login.microsoftonline.com; object-src 'none'; " +
                "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: wss:; script-src 'self'; " +
                (allowInlineStyles ? "style-src 'self' 'unsafe-inline';" : "style-src 'self';");
            await next();
        });
}
