using System.Security.Claims;
using System.Text;
using System.Text.Json.Serialization;
using System.Threading.RateLimiting;
using GPV.ProductTimeFlow.API;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure;
using GPV.ProductTimeFlow.Infrastructure.Hosting;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Identity.Web;
using Microsoft.IdentityModel.Tokens;
using Serilog;

var builder = WebApplication.CreateBuilder(args);

// ── Logging estructurado (sin datos sensibles) ───────────────────────────────
var dataRoot = InfrastructureRegistration.ResolveDataRoot(builder.Configuration, builder.Environment.ContentRootPath);
builder.Host.UseSerilog((ctx, cfg) => cfg.ReadFrom.Configuration(ctx.Configuration)
    .Enrich.FromLogContext().Enrich.WithProperty("App", "TimeFlow.API")
    .WriteTo.Console()
    .WriteTo.File(Path.Combine(dataRoot, "logs", "api-.log"), rollingInterval: RollingInterval.Day, retainedFileCountLimit: 30));

var authMode = builder.Configuration["Authentication:Mode"] ?? "LocalDemo";
InfrastructureRegistration.ValidateEnvironment(builder.Configuration, authMode);

builder.Services.AddTimeFlowApplication();
builder.Services.AddTimeFlowInfrastructure(builder.Configuration, builder.Environment, authMode);
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<TimeFlowExceptionHandler>();
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.Converters.Add(new JsonStringEnumConverter()));
builder.Services.AddOpenApi(o => o.AddDocumentTransformer((doc, _, _) =>
{
    doc.Info.Title = "GPV Product TimeFlow API";
    doc.Info.Version = "v1";
    doc.Info.Description = "API del flujo de solicitudes del Departamento de Producto (tiempo extra, vacaciones y permisos) con autorización de tres filtros.";
    return Task.CompletedTask;
}));
builder.Services.AddSignalR();
builder.Services.AddHttpContextAccessor();

// ── Autenticación ────────────────────────────────────────────────────────────
var jwt = new JwtSettings();
builder.Configuration.GetSection("Authentication:Jwt").Bind(jwt);
if (string.IsNullOrWhiteSpace(jwt.SigningKey))
{
    // DEMO/TEST: llave aleatoria en memoria (los tokens expiran al reiniciar). PRODUCCIÓN usa Entra ID.
    jwt.SigningKey = Convert.ToBase64String(System.Security.Cryptography.RandomNumberGenerator.GetBytes(48));
}
builder.Services.AddSingleton(jwt);
builder.Services.AddSingleton<JwtTokenService>();

if (authMode.Equals("EntraId", StringComparison.OrdinalIgnoreCase))
{
    builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
        .AddMicrosoftIdentityWebApi(builder.Configuration.GetSection("AzureAd"));
    builder.Services.Configure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, o =>
    {
        var previous = o.Events?.OnTokenValidated;
        o.Events ??= new JwtBearerEvents();
        o.Events.OnTokenValidated = async ctx =>
        {
            if (previous is not null) await previous(ctx);
            var auth = ctx.HttpContext.RequestServices.GetRequiredService<AuthService>();
            var oid = ctx.Principal?.FindFirst("http://schemas.microsoft.com/identity/claims/objectidentifier")?.Value ?? ctx.Principal?.FindFirst("oid")?.Value;
            var email = ctx.Principal?.FindFirst("preferred_username")?.Value ?? ctx.Principal?.FindFirst(ClaimTypes.Upn)?.Value;
            var result = await auth.ResolveExternalAsync(oid, email);
            if (result.Outcome != LoginOutcome.Success) { ctx.Fail("Usuario no registrado en TimeFlow."); return; }
            ctx.Principal!.AddIdentity(new ClaimsIdentity(ActorFactory.Claims(result.EmployeeId!.Value, result.Name!, email ?? "", result.Roles, result.SecurityStamp), "TimeFlow"));
        };
    });
}
else
{
    builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme).AddJwtBearer(o =>
    {
        o.MapInboundClaims = false;
        o.TokenValidationParameters = new TokenValidationParameters
        {
            ValidIssuer = jwt.Issuer, ValidAudience = jwt.Audience, IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwt.SigningKey)),
            ValidateIssuer = true, ValidateAudience = true, ValidateLifetime = true, ValidateIssuerSigningKey = true, ClockSkew = TimeSpan.FromMinutes(1),
            NameClaimType = ClaimTypes.Name
        };
        o.Events = new JwtBearerEvents
        {
            // SignalR envía el token por query string en WebSockets.
            OnMessageReceived = ctx =>
            {
                var token = ctx.Request.Query["access_token"];
                if (!string.IsNullOrEmpty(token) && ctx.HttpContext.Request.Path.StartsWithSegments("/hubs")) ctx.Token = token;
                return Task.CompletedTask;
            },
            // Revalida que la cuenta siga activa y sin cambios de rol (SecurityStamp).
            OnTokenValidated = async ctx =>
            {
                var auth = ctx.HttpContext.RequestServices.GetRequiredService<AuthService>();
                var id = int.TryParse(ctx.Principal?.FindFirst(TimeFlowClaims.EmployeeId)?.Value, out var e) ? e : 0;
                var stamp = Guid.TryParse(ctx.Principal?.FindFirst(TimeFlowClaims.SecurityStamp)?.Value, out var s) ? s : Guid.Empty;
                if (!await auth.IsSessionValidAsync(id, stamp)) ctx.Fail("Sesión revocada.");
            }
        };
    });
}
builder.Services.AddAuthorizationBuilder()
    .SetFallbackPolicy(new Microsoft.AspNetCore.Authorization.AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build());

// ── Protección contra abuso ──────────────────────────────────────────────────
var loginPermits = builder.Configuration.GetValue("RateLimiting:LoginPermitsPerMinute", 10);
var apiPermits = builder.Configuration.GetValue("RateLimiting:ApiPermitsPerMinute", 600);
builder.Services.AddRateLimiter(o =>
{
    o.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    o.AddPolicy("login", http => RateLimitPartition.GetFixedWindowLimiter(http.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        _ => new FixedWindowRateLimiterOptions { PermitLimit = loginPermits, Window = TimeSpan.FromMinutes(1) }));
    o.AddPolicy("api", http => RateLimitPartition.GetTokenBucketLimiter(http.User.FindFirst(TimeFlowClaims.EmployeeId)?.Value ?? http.Connection.RemoteIpAddress?.ToString() ?? "anon",
        _ => new TokenBucketRateLimiterOptions { TokenLimit = apiPermits, TokensPerPeriod = apiPermits, ReplenishmentPeriod = TimeSpan.FromMinutes(1), QueueLimit = 0 }));
});
builder.Services.Configure<Microsoft.AspNetCore.Http.Features.FormOptions>(o => o.MultipartBodyLengthLimit = 11 * 1024 * 1024);
builder.WebHost.ConfigureKestrel(k => k.Limits.MaxRequestBodySize = 12 * 1024 * 1024);

var app = builder.Build();

await app.Services.InitializeTimeFlowDatabaseAsync();

app.UseSerilogRequestLogging(o => o.GetLevel = (http, _, ex) => ex is not null || http.Response.StatusCode >= 500 ? Serilog.Events.LogEventLevel.Error : Serilog.Events.LogEventLevel.Information);
app.UseExceptionHandler();
if (!app.Environment.IsDevelopment()) app.UseHsts();
app.UseHttpsRedirection();
app.UseTimeFlowSecurityHeaders(allowInlineStyles: false);
app.UseAuthentication();
app.UseAuthorization();
app.UseRateLimiter();

if (!app.Configuration.GetValue("TimeFlow:Mode", "Demo")!.Equals("Production", StringComparison.OrdinalIgnoreCase))
    app.MapOpenApi().AllowAnonymous();

app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "GPV Product TimeFlow API", version = "4.0.0" })).AllowAnonymous().ExcludeFromDescription();
app.MapHub<NotificationHub>(NotificationHub.Path);
app.MapTimeFlowApi(authMode);

app.Run();

public partial class Program;
