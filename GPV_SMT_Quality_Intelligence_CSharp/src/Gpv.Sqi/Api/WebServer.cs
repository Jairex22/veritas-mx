using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.OData;
using Gpv.Sqi.Services;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Logging;

namespace Gpv.Sqi.Api;

/// <summary>
/// Servidor local (Kestrel):
/// - vinculado a 127.0.0.1 por defecto;
/// - validación del encabezado Host (DNS rebinding) y del Origin;
/// - token CSRF por proceso obligatorio en /api/*;
/// - Content-Security-Policy estricta; límite de 64 KB por solicitud.
/// </summary>
public static class WebServer
{
    public const int MaxBody = 64 * 1024;
    public const string Csp = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; " +
                              "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'";

    private delegate Task<object> Handler(JsonObject body, CancellationToken ct);

    public static WebApplication Build(AppServices ctx, string host, int port, string? webRoot = null)
    {
        var api = new ApiHandlers(ctx);
        var token = InputValidation.NewToken();
        var allowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { $"127.0.0.1:{port}", $"localhost:{port}", $"{host}:{port}" };
        var root = webRoot ?? Path.Combine(AppContext.BaseDirectory, "wwwroot");
        var indexTemplate = File.ReadAllText(Path.Combine(root, "index.html"));
        var files = new PhysicalFileProvider(root);

        var builder = WebApplication.CreateSlimBuilder(new WebApplicationOptions { ContentRootPath = AppContext.BaseDirectory, WebRootPath = root });
        builder.Logging.ClearProviders();
        builder.WebHost.UseKestrel(k =>
        {
            k.AddServerHeader = false;
            k.Limits.MaxRequestBodySize = MaxBody;
            k.Listen(IPAddress.Parse(host), port);
        });
        var app = builder.Build();

        var gets = new Dictionary<string, Handler>
        {
            ["/api/status"] = api.StatusAsync, ["/api/history"] = api.HistoryAsync, ["/api/config"] = api.GetConfigAsync,
            ["/api/diagnostics"] = api.DiagnosticsAsync, ["/api/diagnostics/text"] = api.DiagnosticsTextAsync,
        };
        var posts = new Dictionary<string, Handler>
        {
            ["/api/trace"] = api.TraceAsync, ["/api/pulse"] = api.PulseAsync, ["/api/quality"] = api.QualityAsync,
            ["/api/quality/close-times"] = api.QualityCloseTimesAsync, ["/api/rework"] = api.ReworkAsync,
            ["/api/history/clear"] = api.HistoryClearAsync, ["/api/config"] = api.SaveConfigAsync,
            ["/api/config/reset"] = api.ResetConfigAsync, ["/api/diagnostics/test"] = api.DiagnosticsTestAsync,
            ["/api/logs/open"] = api.OpenLogsAsync,
        };

        app.Run(async http =>
        {
            var req = http.Request; var res = http.Response;
            res.Headers["Content-Security-Policy"] = Csp;
            res.Headers["X-Content-Type-Options"] = "nosniff";
            res.Headers["X-Frame-Options"] = "DENY";
            res.Headers["Referrer-Policy"] = "no-referrer";
            res.Headers["Cache-Control"] = "no-store";
            try
            {
                if (!allowed.Contains(req.Host.Value ?? "")) { await JsonOut(res, 403, Err("Host no permitido")); return; }
                var path = req.Path.Value ?? "/";
                if (path.StartsWith("/api/", StringComparison.Ordinal))
                {
                    await ApiAsync(http, path, token, allowed, gets, posts, api);
                    return;
                }
                if (req.Method != "GET" && req.Method != "HEAD") { await JsonOut(res, 404, Err("No encontrado")); return; }
                if (path is "/" or "/index.html")
                {
                    await Bytes(res, 200, Encoding.UTF8.GetBytes(indexTemplate.Replace("{{CSRF_TOKEN}}", token)), "text/html; charset=utf-8");
                    return;
                }
                if (path.StartsWith("/static/", StringComparison.Ordinal))
                {
                    var rel = path["/static/".Length..];
                    var info = rel.Contains("..") || rel.Contains('\\') || rel.Contains('%') ? null : files.GetFileInfo(rel);
                    if (info is null || !info.Exists || info.IsDirectory || info.PhysicalPath is null
                        || !Path.GetFullPath(info.PhysicalPath).StartsWith(Path.GetFullPath(root), StringComparison.Ordinal))
                    { await JsonOut(res, 404, Err("No encontrado")); return; }
                    await Bytes(res, 200, await File.ReadAllBytesAsync(info.PhysicalPath, http.RequestAborted), ContentType(info.Name));
                    return;
                }
                await JsonOut(res, 404, Err("No encontrado"));
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                AppLog.Error("server", $"Error no controlado en {req.Path}", ex);
                if (!res.HasStarted) await JsonOut(res, 500, Err("Error interno de la aplicación. Revise los logs."));
            }
        });
        return app;
    }

    private static Dictionary<string, object?> Err(string message) => new() { ["error"] = message };

    private static string ContentType(string name) => Path.GetExtension(name).ToLowerInvariant() switch
    {
        ".js" => "text/javascript; charset=utf-8",
        ".css" => "text/css; charset=utf-8",
        ".svg" => "image/svg+xml; charset=utf-8",
        ".html" => "text/html; charset=utf-8",
        ".png" => "image/png",
        ".json" => "application/json; charset=utf-8",
        _ => "application/octet-stream",
    };

    private static async Task Bytes(HttpResponse res, int status, byte[] body, string contentType, string? disposition = null)
    {
        res.StatusCode = status;
        res.ContentType = contentType;
        res.ContentLength = body.Length;
        if (disposition is not null) res.Headers.ContentDisposition = disposition;
        if (!HttpMethods.IsHead(res.HttpContext.Request.Method)) await res.Body.WriteAsync(body);
    }

    private static Task JsonOut(HttpResponse res, int status, object payload) =>
        Bytes(res, status, Encoding.UTF8.GetBytes(Json.Serialize(payload)), "application/json; charset=utf-8");

    private static async Task ApiAsync(HttpContext http, string path, string token, HashSet<string> allowed,
        Dictionary<string, Handler> gets, Dictionary<string, Handler> posts, ApiHandlers api)
    {
        var req = http.Request; var res = http.Response; var ct = http.RequestAborted;
        JsonObject body = new();
        if (req.Method == "POST")
        {
            if (req.ContentLength is > MaxBody) { await JsonOut(res, 413, Err("Solicitud demasiado grande")); return; }
            string raw;
            try
            {
                using var reader = new StreamReader(req.Body, Encoding.UTF8);
                raw = await reader.ReadToEndAsync(ct);
            }
            catch (Microsoft.AspNetCore.Http.BadHttpRequestException) { await JsonOut(res, 413, Err("Solicitud demasiado grande")); return; }
            if (raw.Length > MaxBody) { await JsonOut(res, 413, Err("Solicitud demasiado grande")); return; }
            if (!(req.ContentType ?? "").Contains("json", StringComparison.OrdinalIgnoreCase))
            { await JsonOut(res, 415, Err("Se requiere JSON")); return; }
            try { body = InputValidation.ParseBody(raw); }
            catch (InputException ex) { await JsonOut(res, 400, Err(ex.Message)); return; }
        }
        else if (req.Method != "GET") { await JsonOut(res, 404, Err("Ruta no encontrada")); return; }

        var origin = req.Headers.Origin.ToString();
        var originOk = string.IsNullOrEmpty(origin) || (Uri.TryCreate(origin, UriKind.Absolute, out var o) && allowed.Contains(o.Authority));
        if (req.Headers["X-CSRF-Token"].ToString() != token || !originOk)
        { await JsonOut(res, 403, Err("Token CSRF inválido u origen no permitido")); return; }

        try
        {
            if (req.Method == "POST" && path == "/api/report")
            {
                var (data, contentType, fileName) = await api.ReportAsync(body, ct);
                await Bytes(res, 200, data, contentType, $"attachment; filename=\"{fileName}\"");
                return;
            }
            var routes = req.Method == "POST" ? posts : gets;
            if (!routes.TryGetValue(path, out var handler)) { await JsonOut(res, 404, Err("Ruta no encontrada")); return; }
            await JsonOut(res, 200, await handler(body, ct));
        }
        catch (Exception ex) when (ex is InputException or FilterException)
        {
            await JsonOut(res, 400, Err(ex.Message));
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            AppLog.Error("server", $"Error no controlado en {path}", ex);
            await JsonOut(res, 500, Err("Error interno de la aplicación. Revise los logs."));
        }
    }
}
