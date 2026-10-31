using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure.Hosting;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;

namespace GPV.ProductTimeFlow.Web;

public sealed record AuthModeInfo(string Mode)
{
    public bool IsEntraId => Mode.Equals("EntraId", StringComparison.OrdinalIgnoreCase);
}

/// <summary>
/// Endpoints HTTP de la aplicación web: descargas protegidas por cookie (PDF, adjuntos, Excel) y cierre de sesión.
/// La autorización por recurso la aplican los servicios de Application.
/// </summary>
public static class WebEndpoints
{
    public static void MapTimeFlowWebEndpoints(this WebApplication app, string authMode)
    {
        static Actor Actor(HttpContext http) => ActorFactory.FromPrincipal(http.User, http) ?? throw new ForbiddenException();

        var files = app.MapGroup("/files").RequireAuthorization();

        files.MapGet("/requests/{id:guid}/pdf", async (Guid id, bool? download, HttpContext http, DocumentService docs, CancellationToken ct) =>
        {
            var file = await docs.RequestPdfAsync(Actor(http), id, ct);
            return download == true ? Results.File(file.Content, file.ContentType, file.FileName) : Results.File(file.Content, file.ContentType);
        });

        files.MapGet("/attachments/{id:guid}", async (Guid id, HttpContext http, DocumentService docs, IFileStorage storage, CancellationToken ct) =>
        {
            var (meta, stream) = await docs.AttachmentAsync(Actor(http), id, storage, ct);
            return Results.File(stream, meta.ContentType, meta.FileName);
        });

        files.MapGet("/exports/requests.xlsx", async (string? set, RequestKind? kind, int? employeeId, DateOnly? from, DateOnly? to, HttpContext http, ExportService export, CancellationToken ct) =>
        {
            var file = await export.ExportAsync(Actor(http), new ExportFilter { Set = set ?? "approved", Kind = kind, EmployeeId = employeeId, From = from, To = to }, ct);
            return Results.File(file.Content, file.ContentType, file.FileName);
        });

        files.MapGet("/templates/employees.xlsx", async (HttpContext http, ActorGuard guard, ExportService export, CancellationToken ct) =>
        {
            await guard.RequireRoleAsync(Actor(http), UserRole.ProductAdmin, ct);
            var file = export.ImportTemplate();
            return Results.File(file.Content, file.ContentType, file.FileName);
        });

        files.MapGet("/emails/{id:guid}", async (Guid id, HttpContext http, EmailMonitorService emails, CancellationToken ct) =>
        {
            var html = await emails.PreviewHtmlAsync(Actor(http), id, ct);
            if (html is null) return Results.NotFound();
            // Vista previa aislada: sin scripts ni recursos externos.
            http.Response.Headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'";
            http.Response.Headers["X-Frame-Options"] = "SAMEORIGIN";
            return Results.Content(html, "text/html; charset=utf-8");
        });

        app.MapPost("/account/logout", async (HttpContext http, Microsoft.AspNetCore.Antiforgery.IAntiforgery antiforgery) =>
        {
            if (!await antiforgery.IsRequestValidAsync(http)) return Results.BadRequest();
            await http.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
            if (authMode.Equals("EntraId", StringComparison.OrdinalIgnoreCase))
                return Results.SignOut(new AuthenticationProperties { RedirectUri = "/" }, [CookieAuthenticationDefaults.AuthenticationScheme, OpenIdConnectDefaults.AuthenticationScheme]);
            return Results.LocalRedirect("/account/login?loggedOut=1");
        }).RequireAuthorization();

        if (authMode.Equals("EntraId", StringComparison.OrdinalIgnoreCase))
            app.MapGet("/account/entra", (string? returnUrl) => Results.Challenge(new AuthenticationProperties { RedirectUri = SafeReturnUrl(returnUrl) }, [OpenIdConnectDefaults.AuthenticationScheme]));
    }

    public static string SafeReturnUrl(string? returnUrl) =>
        !string.IsNullOrEmpty(returnUrl) && returnUrl.StartsWith('/') && !returnUrl.StartsWith("//") && !returnUrl.StartsWith("/\\") ? returnUrl : "/";
}
