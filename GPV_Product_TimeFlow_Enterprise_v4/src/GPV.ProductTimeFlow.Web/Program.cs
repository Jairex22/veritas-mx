using System.Security.Claims;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure;
using GPV.ProductTimeFlow.Infrastructure.Hosting;
using GPV.ProductTimeFlow.Web;
using GPV.ProductTimeFlow.Web.Components;
using GPV.ProductTimeFlow.Web.Services;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Identity.Web;
using Serilog;

var builder = WebApplication.CreateBuilder(args);

var dataRoot = InfrastructureRegistration.ResolveDataRoot(builder.Configuration, builder.Environment.ContentRootPath);
builder.Host.UseSerilog((ctx, cfg) => cfg.ReadFrom.Configuration(ctx.Configuration)
    .Enrich.FromLogContext().Enrich.WithProperty("App", "TimeFlow.Web")
    .WriteTo.Console()
    .WriteTo.File(Path.Combine(dataRoot, "logs", "web-.log"), rollingInterval: RollingInterval.Day, retainedFileCountLimit: 30));

var authMode = builder.Configuration["Authentication:Mode"] ?? "LocalDemo";
InfrastructureRegistration.ValidateEnvironment(builder.Configuration, authMode);

builder.Services.AddTimeFlowApplication();
builder.Services.AddTimeFlowInfrastructure(builder.Configuration, builder.Environment, authMode);
builder.Services.AddProblemDetails();
builder.Services.AddExceptionHandler<TimeFlowExceptionHandler>();
builder.Services.AddRazorComponents().AddInteractiveServerComponents(o => o.DetailedErrors = builder.Environment.IsDevelopment());
builder.Services.AddSignalR();
builder.Services.AddHttpContextAccessor();
builder.Services.AddCascadingAuthenticationState();
builder.Services.AddScoped<UserSession>();
builder.Services.AddScoped<ServiceRunner>();
builder.Services.AddScoped<ToastService>();
builder.Services.AddSingleton<LoginThrottle>();
builder.Services.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(dataRoot, "keys"))).SetApplicationName("GPV.ProductTimeFlow.Web");

// Cookies: siempre "Secure" con prefijo __Host- fuera de Development. En Development se permite HTTP local (pruebas E2E).
var strictCookies = !builder.Environment.IsDevelopment();
var cookiePolicy = strictCookies ? CookieSecurePolicy.Always : CookieSecurePolicy.SameAsRequest;
var cookiePrefix = strictCookies ? "__Host-" : "";

// ── Autenticación: cookies seguras (DEMO/TEST) u OpenID Connect con Microsoft Entra ID (producción) ──
if (authMode.Equals("EntraId", StringComparison.OrdinalIgnoreCase))
{
    builder.Services.AddAuthentication(OpenIdConnectDefaults.AuthenticationScheme)
        .AddMicrosoftIdentityWebApp(builder.Configuration.GetSection("AzureAd"));
    builder.Services.Configure<OpenIdConnectOptions>(OpenIdConnectDefaults.AuthenticationScheme, o =>
    {
        var previous = o.Events.OnTokenValidated;
        o.Events.OnTokenValidated = async ctx =>
        {
            if (previous is not null) await previous(ctx);
            var auth = ctx.HttpContext.RequestServices.GetRequiredService<AuthService>();
            var oid = ctx.Principal?.FindFirst("http://schemas.microsoft.com/identity/claims/objectidentifier")?.Value ?? ctx.Principal?.FindFirst("oid")?.Value;
            var email = ctx.Principal?.FindFirst("preferred_username")?.Value ?? ctx.Principal?.FindFirst(ClaimTypes.Email)?.Value;
            var result = await auth.ResolveExternalAsync(oid, email);
            if (result.Outcome != LoginOutcome.Success) { ctx.Fail("Su cuenta corporativa no está registrada en GPV Product TimeFlow."); return; }
            ctx.Principal!.AddIdentity(new ClaimsIdentity(ActorFactory.Claims(result.EmployeeId!.Value, result.Name!, email ?? "", result.Roles, result.SecurityStamp), "TimeFlow"));
        };
    });
}
else
{
    builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie(o =>
    {
        o.LoginPath = "/account/login";
        o.LogoutPath = "/account/logout";
        o.AccessDeniedPath = "/acceso-denegado";
        o.Cookie.Name = cookiePrefix + "TimeFlow";
        o.Cookie.HttpOnly = true;
        o.Cookie.SecurePolicy = cookiePolicy;
        o.Cookie.SameSite = SameSiteMode.Strict;
        o.ExpireTimeSpan = TimeSpan.FromHours(8);
        o.SlidingExpiration = true;
        o.Events.OnValidatePrincipal = async ctx =>
        {
            // Sesión revocada si cambian roles, se desactiva la cuenta o se reinicia el sello de seguridad.
            var id = int.TryParse(ctx.Principal?.FindFirst(GPV.ProductTimeFlow.Infrastructure.TimeFlowClaims.EmployeeId)?.Value, out var e) ? e : 0;
            var stamp = Guid.TryParse(ctx.Principal?.FindFirst(GPV.ProductTimeFlow.Infrastructure.TimeFlowClaims.SecurityStamp)?.Value, out var s) ? s : Guid.Empty;
            var auth = ctx.HttpContext.RequestServices.GetRequiredService<AuthService>();
            if (!await auth.IsSessionValidAsync(id, stamp))
            {
                ctx.RejectPrincipal();
                await ctx.HttpContext.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
            }
        };
    });
}
builder.Services.AddAuthorization();
builder.Services.AddAntiforgery(o => { o.Cookie.Name = cookiePrefix + "TimeFlow-AF"; o.Cookie.SecurePolicy = cookiePolicy; });
builder.Services.AddSingleton(new AuthModeInfo(authMode));

var app = builder.Build();

await app.Services.InitializeTimeFlowDatabaseAsync();

app.UseSerilogRequestLogging(o => o.GetLevel = (http, _, ex) => ex is not null || http.Response.StatusCode >= 500 ? Serilog.Events.LogEventLevel.Error : Serilog.Events.LogEventLevel.Information);
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error", createScopeForErrors: true);
    app.UseHsts();
}
app.UseStatusCodePagesWithReExecute("/not-found", createScopeForStatusCodePages: true);
app.UseHttpsRedirection();
app.UseTimeFlowSecurityHeaders();
app.UseAuthentication();
app.UseAuthorization();
app.UseAntiforgery();

app.MapStaticAssets();
app.MapRazorComponents<App>().AddInteractiveServerRenderMode();
app.MapHub<NotificationHub>(NotificationHub.Path).RequireAuthorization();
app.MapTimeFlowWebEndpoints(authMode);
app.MapGet("/health", () => Results.Ok(new { status = "ok", service = "GPV Product TimeFlow Web", version = "4.0.0" })).AllowAnonymous();

app.Run();

public partial class Program;
