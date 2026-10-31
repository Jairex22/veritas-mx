using System.IdentityModel.Tokens.Jwt;
using System.Text;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure.Hosting;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Mvc;
using Microsoft.IdentityModel.Tokens;

namespace GPV.ProductTimeFlow.API;

public sealed class JwtSettings
{
    public string Issuer { get; set; } = "gpv-product-timeflow";
    public string Audience { get; set; } = "gpv-product-timeflow-clients";
    /// <summary>Solo vía variable de entorno Authentication__Jwt__SigningKey o almacén seguro. Mínimo 32 bytes.</summary>
    public string SigningKey { get; set; } = "";
    public int LifetimeMinutes { get; set; } = 480;
}

public sealed class JwtTokenService(JwtSettings settings, TimeProvider time)
{
    public (string Token, DateTime ExpiresAtUtc) Issue(int employeeId, string name, string email, UserRole roles, Guid stamp)
    {
        var expires = time.GetUtcNow().UtcDateTime.AddMinutes(settings.LifetimeMinutes);
        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(settings.SigningKey));
        var token = new JwtSecurityToken(settings.Issuer, settings.Audience, ActorFactory.Claims(employeeId, name, email, roles, stamp),
            notBefore: time.GetUtcNow().UtcDateTime, expires: expires, signingCredentials: new SigningCredentials(key, SecurityAlgorithms.HmacSha256));
        return (new JwtSecurityTokenHandler().WriteToken(token), expires);
    }
}

/// <summary>Endpoints REST v1. Toda la autorización por recurso ocurre en la capa Application.</summary>
public static class Endpoints
{
    private static Actor Actor(HttpContext http) => ActorFactory.FromPrincipal(http.User, http) ?? throw new ForbiddenException("Sesión inválida.");

    public static void MapTimeFlowApi(this WebApplication app, string authMode)
    {
        var api = app.MapGroup("/api/v1").RequireRateLimiting("api");

        // ── Autenticación (solo DEMO/TEST) ──
        if (!authMode.Equals("EntraId", StringComparison.OrdinalIgnoreCase))
        {
            api.MapPost("/auth/login", async ([FromBody] LoginRequest body, HttpContext http, AuthService auth, JwtTokenService tokens, RequestQueryService queries, CancellationToken ct) =>
            {
                var result = await auth.ValidateAsync(body.Email, body.Password, http.Connection.RemoteIpAddress?.ToString(), ct);
                if (result.Outcome != LoginOutcome.Success)
                    return Results.Problem(result.Message, statusCode: result.Outcome == LoginOutcome.LockedOut ? StatusCodes.Status423Locked : StatusCodes.Status401Unauthorized, title: "Autenticación");
                var profile = await queries.GetProfileAsync(result.EmployeeId!.Value, ct);
                var (token, expires) = tokens.Issue(profile.EmployeeId, profile.FullName, profile.Email, result.Roles, result.SecurityStamp);
                return Results.Ok(new LoginResponse(token, expires, profile));
            }).AllowAnonymous().RequireRateLimiting("login").WithSummary("Inicio de sesión DEMO (devuelve JWT).");
        }

        api.MapGet("/me", (HttpContext http, RequestQueryService q, CancellationToken ct) => q.GetProfileAsync(Actor(http).EmployeeId, ct));
        api.MapGet("/dashboard", (HttpContext http, RequestQueryService q, CancellationToken ct) => q.GetDashboardAsync(Actor(http), ct));
        api.MapGet("/search", (string term, HttpContext http, RequestQueryService q, CancellationToken ct) => q.SearchAsync(Actor(http), term, ct));

        // ── Solicitudes ──
        var requests = api.MapGroup("/requests").WithTags("Solicitudes");
        requests.MapGet("/", (RequestScope? scope, RequestStatus? status, RequestKind? kind, DateOnly? from, DateOnly? to, int? employeeId, string? search, string? bucket, int? page, int? pageSize,
            HttpContext http, RequestQueryService q, CancellationToken ct) =>
            q.ListAsync(Actor(http), new RequestQuery
            {
                Scope = scope ?? RequestScope.Mine, Status = status, Kind = kind, From = from, To = to, EmployeeId = employeeId,
                Search = search, Bucket = bucket, Page = page ?? 1, PageSize = pageSize ?? 20
            }, ct));
        requests.MapGet("/{id:guid}", (Guid id, HttpContext http, RequestQueryService q, CancellationToken ct) => q.GetDetailAsync(Actor(http), id, true, ct));
        requests.MapPost("/", async ([FromBody] RequestInput input, HttpContext http, WorkflowService wf, RequestQueryService q, CancellationToken ct) =>
        {
            var actor = Actor(http);
            var id = await wf.CreateDraftAsync(actor, input, ct);
            return Results.Created($"/api/v1/requests/{id}", await q.GetDetailAsync(actor, id, true, ct));
        });
        requests.MapPut("/{id:guid}", async (Guid id, [FromBody] RequestInput input, HttpContext http, WorkflowService wf, RequestQueryService q, CancellationToken ct) =>
        {
            var actor = Actor(http);
            await wf.UpdateDraftAsync(actor, id, input, ct);
            return await q.GetDetailAsync(actor, id, true, ct);
        });
        requests.MapPost("/{id:guid}/submit", (Guid id, [FromBody] SubmitInput input, HttpContext http, WorkflowService wf, CancellationToken ct) =>
            wf.SubmitAsync(Actor(http), id, WithHeaderKey(http, input), ct));
        requests.MapPost("/{id:guid}/decision", (Guid id, [FromBody] DecisionInput input, HttpContext http, WorkflowService wf, CancellationToken ct) =>
        {
            if (http.Request.Headers.TryGetValue("Idempotency-Key", out var key) && key.ToString().Length >= 8) input.IdempotencyKey = key!;
            return wf.DecideAsync(Actor(http), id, input, ct);
        });
        requests.MapPost("/{id:guid}/administrative", (Guid id, [FromBody] AdministrativeInput input, HttpContext http, WorkflowService wf, CancellationToken ct) =>
        {
            if (http.Request.Headers.TryGetValue("Idempotency-Key", out var key) && key.ToString().Length >= 8) input.IdempotencyKey = key!;
            return wf.AdministrativeAsync(Actor(http), id, input, ct);
        });
        requests.MapPost("/{id:guid}/cancel", (Guid id, [FromBody] CancelInput input, HttpContext http, WorkflowService wf, CancellationToken ct) => wf.CancelAsync(Actor(http), id, input, ct));
        requests.MapPost("/{id:guid}/attachments", async (Guid id, IFormFile file, HttpContext http, WorkflowService wf, CancellationToken ct) =>
        {
            await using var stream = file.OpenReadStream();
            return await wf.AddAttachmentAsync(Actor(http), id, file.FileName, file.ContentType, stream, file.Length, ct);
        }).DisableAntiforgery();
        requests.MapDelete("/{id:guid}/attachments/{attachmentId:guid}", async (Guid id, Guid attachmentId, HttpContext http, WorkflowService wf, CancellationToken ct) =>
        {
            await wf.RemoveAttachmentAsync(Actor(http), id, attachmentId, ct);
            return Results.NoContent();
        });
        requests.MapGet("/{id:guid}/pdf", async (Guid id, HttpContext http, DocumentService docs, CancellationToken ct) =>
        {
            var file = await docs.RequestPdfAsync(Actor(http), id, ct);
            return Results.File(file.Content, file.ContentType, file.FileName);
        });
        api.MapGet("/attachments/{id:guid}", async (Guid id, HttpContext http, DocumentService docs, IFileStorage storage, CancellationToken ct) =>
        {
            var (meta, stream) = await docs.AttachmentAsync(Actor(http), id, storage, ct);
            return Results.File(stream, meta.ContentType, meta.FileName);
        });

        // ── Cálculos, saldos y calendario ──
        api.MapGet("/vacations/balance", (int? employeeId, int? year, HttpContext http, VacationService v, CancellationToken ct) => v.GetBalanceAsync(Actor(http), employeeId, year, ct));
        api.MapPost("/vacations/preview", ([FromBody] VacationPreviewRequest r, HttpContext http, VacationService v, CancellationToken ct) => v.PreviewAsync(Actor(http), r, ct));
        api.MapPost("/overtime/preview", ([FromBody] OvertimePreviewRequest r, HttpContext http, OvertimeService o, CancellationToken ct) => o.PreviewAsync(Actor(http), r, ct));
        api.MapGet("/overtime/summary", (int year, int month, int? employeeId, HttpContext http, OvertimeService o, CancellationToken ct) => o.MonthlySummaryAsync(Actor(http), year, month, employeeId, ct));
        api.MapGet("/calendar", (DateOnly from, DateOnly to, CalendarScope? scope, HttpContext http, RequestQueryService q, CancellationToken ct) =>
            q.GetCalendarAsync(Actor(http), from, to, scope ?? CalendarScope.Mine, ct));
        api.MapGet("/catalogs/leave-categories", (RequestKind? kind, SettingsAdminService s, CancellationToken ct) => s.CategoriesAsync(kind, true, ct));
        api.MapGet("/catalogs/holidays", (int? year, SettingsAdminService s, CancellationToken ct) => s.HolidaysAsync(year, ct));

        // ── Notificaciones ──
        api.MapGet("/notifications", (bool? unreadOnly, int? page, HttpContext http, NotificationService n, CancellationToken ct) => n.ListAsync(Actor(http), unreadOnly ?? false, page ?? 1, 20, ct));
        api.MapGet("/notifications/unread-count", (HttpContext http, NotificationService n, CancellationToken ct) => n.UnreadCountAsync(Actor(http), ct));
        api.MapPost("/notifications/{id:guid}/read", async (Guid id, HttpContext http, NotificationService n, CancellationToken ct) => { await n.MarkReadAsync(Actor(http), id, ct); return Results.NoContent(); });
        api.MapPost("/notifications/read-all", async (HttpContext http, NotificationService n, CancellationToken ct) => Results.Ok(await n.MarkAllReadAsync(Actor(http), ct)));

        // ── Exportación ──
        api.MapGet("/exports/requests.xlsx", async (string? set, RequestKind? kind, int? employeeId, DateOnly? from, DateOnly? to, HttpContext http, ExportService e, CancellationToken ct) =>
        {
            var filter = new ExportFilter { Set = set ?? "approved", Kind = kind, EmployeeId = employeeId, From = from, To = to };
            var file = await e.ExportAsync(Actor(http), filter, ct);
            return Results.File(file.Content, file.ContentType, file.FileName);
        });

        // ── Administración de Producto ──
        var admin = api.MapGroup("/admin").WithTags("Administración");
        admin.MapGet("/employees", (string? search, bool? includeInactive, int? page, int? pageSize, HttpContext http, EmployeeAdminService s, CancellationToken ct) =>
            s.ListAsync(Actor(http), search, includeInactive ?? false, page ?? 1, pageSize ?? 50, ct));
        admin.MapGet("/employees/{id:int}", (int id, HttpContext http, EmployeeAdminService s, CancellationToken ct) => s.GetAsync(Actor(http), id, ct));
        admin.MapPost("/employees", async ([FromBody] EmployeeInput input, HttpContext http, EmployeeAdminService s, CancellationToken ct) =>
        {
            var id = await s.CreateAsync(Actor(http), input, ct);
            return Results.Created($"/api/v1/admin/employees/{id}", new { id });
        });
        admin.MapPut("/employees/{id:int}", async (int id, [FromBody] EmployeeInput input, HttpContext http, EmployeeAdminService s, CancellationToken ct) =>
        {
            await s.UpdateAsync(Actor(http), id, input, ct);
            return Results.NoContent();
        });
        admin.MapPost("/employees/import", async (IFormFile file, bool? dryRun, HttpContext http, EmployeeAdminService s, CancellationToken ct) =>
        {
            await using var stream = file.OpenReadStream();
            return await s.ImportAsync(Actor(http), stream, dryRun ?? true, ct);
        }).DisableAntiforgery();
        admin.MapGet("/settings/policy", async (HttpContext http, ActorGuard g, SettingsAdminService s, CancellationToken ct) =>
        {
            await g.RequireRoleAsync(Actor(http), UserRole.ProductAdmin, ct);
            return await s.GetPolicyAsync(ct);
        });
        admin.MapPut("/settings/policy", async ([FromBody] PolicySettingsDto dto, HttpContext http, SettingsAdminService s, CancellationToken ct) =>
        {
            await s.UpdatePolicyAsync(Actor(http), dto, ct);
            return Results.NoContent();
        });
        admin.MapGet("/audit", (string? search, int? page, HttpContext http, AuditService a, CancellationToken ct) => a.ListAsync(Actor(http), search, page ?? 1, 50, ct));
        admin.MapGet("/audit/verify", (HttpContext http, AuditService a, CancellationToken ct) => a.VerifyAsync(Actor(http), ct));
        admin.MapGet("/emails", (EmailStatus? status, int? page, HttpContext http, EmailMonitorService m, CancellationToken ct) => m.ListAsync(Actor(http), status, page ?? 1, 50, ct));
        admin.MapGet("/health", (HttpContext http, HealthService h, CancellationToken ct) => h.GetAsync(Actor(http), ct));

        // ── Verificación pública por QR (sin datos personales) ──
        app.MapGet("/api/v1/verify/{folio}", async (string folio, string? c, RequestQueryService q, CancellationToken ct) =>
            await q.VerifyAsync(folio, c, ct) is { } v ? Results.Ok(v) : Results.NotFound()).AllowAnonymous().RequireRateLimiting("login");
    }

    private static SubmitInput WithHeaderKey(HttpContext http, SubmitInput input)
    {
        if (http.Request.Headers.TryGetValue("Idempotency-Key", out var key) && key.ToString().Length >= 8) input.IdempotencyKey = key!;
        return input;
    }
}
