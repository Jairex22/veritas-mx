using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Gpv.Sqi.Config;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;
using Gpv.Sqi.Reports;
using Gpv.Sqi.Services;

namespace Gpv.Sqi.Api;

/// <summary>Manejadores de la API JSON (mismo contrato que la versión Python; el frontend es idéntico).</summary>
public sealed class ApiHandlers(AppServices ctx)
{
    private static readonly Dictionary<string, TimeSpan> DiagWindows = new()
    {
        ["SMT"] = TimeSpan.FromHours(1), ["Quality"] = TimeSpan.FromHours(24), ["QualityHistory"] = TimeSpan.FromHours(24),
    };

    private string? PolicyBlock() => ctx.Config.Mode == "live" ? ctx.Source.PolicyCheck("*")?.Error : null;

    private bool? CredentialConfigured() => ctx.Config.Str("odata.auth_method") == "basic" ? Credentials.IsConfigured(ctx.Config) : null;

    // ------------------------------------------------------------- estado
    public Task<object> StatusAsync(JsonObject _, CancellationToken ct)
    {
        var cfg = ctx.Config;
        return Task.FromResult<object>(new Dictionary<string, object?>
        {
            ["app"] = cfg.Str("app.name"), ["site"] = cfg.Str("app.site"), ["version"] = AppConfig.AppVersion,
            ["mode"] = cfg.Mode, ["is_demo"] = cfg.Mode != "live", ["policy_block"] = PolicyBlock(),
            ["health"] = ctx.Audit.Health(ctx.DataSource),
            ["pulse_auto_refresh"] = cfg.Bool("pulse.auto_refresh_enabled"),
            ["pulse_interval"] = cfg.Int("pulse.refresh_interval_seconds"),
            ["display_utc_offset"] = cfg.Str("app.display_utc_offset"),
            ["server_time"] = TimeParse.NowUtcIso(),
        });
    }

    // ------------------------------------------------------------- módulos
    public async Task<object> TraceAsync(JsonObject body, CancellationToken ct) =>
        await new TraceabilityService(ctx).TraceAsync(InputValidation.Identifier(body), ct);

    public async Task<object> PulseAsync(JsonObject body, CancellationToken ct) => await new PulseService(ctx).PulseAsync(body, ct);

    public async Task<object> QualityAsync(JsonObject body, CancellationToken ct) => await new QualityService(ctx).DashboardAsync(body, ct);

    public async Task<object> QualityCloseTimesAsync(JsonObject body, CancellationToken ct)
    {
        if (body["defect_ids"] is not JsonArray ids || ids.Count > 50) throw new InputException("Lista de DefectID inválida");
        return await new QualityService(ctx).CloseTimesAsync(ids, ct);
    }

    public async Task<object> ReworkAsync(JsonObject body, CancellationToken ct)
    {
        var batch = body["batch"];
        if (batch is not null && !(batch is JsonValue bv && bv.TryGetValue<string>(out var bs) && bs.Length == 0))
            return await new ReworkService(ctx).ByBatchAsync(body, ct);
        return await new ReworkService(ctx).ByIdentifierAsync(InputValidation.Identifier(body), ct);
    }

    public Task<object> HistoryAsync(JsonObject _, CancellationToken ct) => Task.FromResult<object>(new Dictionary<string, object?>
    {
        ["searches"] = ctx.Audit.Searches(200), ["queries"] = ctx.Audit.RecentQueries(100),
    });

    public Task<object> HistoryClearAsync(JsonObject _, CancellationToken ct)
    {
        ctx.Audit.ClearSearches();
        return Task.FromResult<object>(new Dictionary<string, object?> { ["ok"] = true });
    }

    public async Task<(byte[] Data, string ContentType, string FileName)> ReportAsync(JsonObject body, CancellationToken ct)
    {
        var identifier = InputValidation.Identifier(body);
        var fmt = InputValidation.GetString(body, "format") ?? "csv";
        if (!Exporters.All.TryGetValue(fmt, out var exporter)) throw new InputException("Formato de reporte no soportado");
        var trace = ctx.Audit.LatestAnalysis(ctx.DataSource, "trace", identifier)
                    ?? JsonNode.Parse(Json.Serialize(await new TraceabilityService(ctx).TraceAsync(identifier, ct)))!.AsObject();
        var data = exporter.Func(ReportBuilder.Build(trace));
        var prefix = trace["is_demo"]?.GetValue<bool>() == true ? "DEMO_" : "";
        var safe = new string(identifier.Select(c => char.IsAsciiLetterOrDigit(c) || c is '-' or '_' ? c : '_').ToArray());
        return (data, exporter.ContentType, $"{prefix}GPV_Reporte_{safe}.{exporter.Ext}");
    }

    // ------------------------------------------------------------- configuración
    public Task<object> GetConfigAsync(JsonObject _, CancellationToken ct)
    {
        var view = ctx.Config.PublicView();
        view["credential_configured"] = CredentialConfigured();
        return Task.FromResult<object>(view);
    }

    public async Task<object> SaveConfigAsync(JsonObject body, CancellationToken ct)
    {
        if (body["values"] is not JsonObject values || values.Count == 0) throw new InputException("No se recibieron valores");
        var clean = new Dictionary<string, JsonNode>();
        foreach (var (k, v) in values)
        {
            try { clean[k] = AppConfig.ValidateSetting(k, v); }
            catch (ConfigException ex) { throw new InputException(ex.Message); }
        }
        ctx.Settings.Save(clean);
        ctx.Reload();
        return await GetConfigAsync(body, ct);
    }

    public async Task<object> ResetConfigAsync(JsonObject body, CancellationToken ct)
    {
        ctx.Settings.Reset();
        ctx.Reload();
        return await GetConfigAsync(body, ct);
    }

    // ------------------------------------------------------------- diagnóstico
    public Task<object> DiagnosticsAsync(JsonObject _, CancellationToken ct)
    {
        var cfg = ctx.Config;
        var url = new Uri(cfg.Str("odata.base_url"));
        return Task.FromResult<object>(new Dictionary<string, object?>
        {
            ["mode"] = cfg.Mode, ["version"] = AppConfig.AppVersion,
            ["base_url"] = cfg.Str("odata.base_url"), ["scheme"] = url.Scheme, ["host"] = url.Host, ["port"] = url.Port,
            ["auth_method"] = cfg.Str("odata.auth_method"), ["credential_source"] = cfg.Str("odata.credential_source"),
            ["credential_configured"] = CredentialConfigured(),
            ["timeout_seconds"] = cfg.Num("odata.timeout_seconds"),
            ["connect_timeout_seconds"] = cfg.Node("odata.connect_timeout_seconds") is null ? null : cfg.Num("odata.connect_timeout_seconds"),
            ["max_retries"] = cfg.Int("odata.max_retries"),
            ["max_concurrent_requests"] = cfg.Int("odata.max_concurrent_requests"),
            ["policy_block"] = PolicyBlock(),
            ["security"] = cfg.Node("security")?.DeepClone(),
            ["health"] = ctx.Audit.Health(ctx.DataSource),
            ["recent_queries"] = ctx.Audit.RecentQueries(30),
            ["metadata_status"] = ctx.Source.LastMetadataStatus,
            ["cache_counts"] = ctx.Cache.Counts(),
            ["entities"] = Entities.Names.ToList(),
            ["python"] = ".NET " + Environment.Version,   // clave conservada por compatibilidad con el frontend
            ["platform"] = RuntimeInformation.OSDescription,
        });
    }

    public async Task<object> DiagnosticsTestAsync(JsonObject body, CancellationToken ct)
    {
        var entity = InputValidation.GetString(body, "entity");
        if (entity == "$metadata")
        {
            var (res, meta) = await ctx.Source.FetchMetadataAsync(ct);
            if (ctx.DataSource == "demo") ctx.Audit.RecordQuery(res);
            var outD = new Dictionary<string, object?> { ["result"] = res.ToStatusDict() };
            if (meta is not null)
            {
                outD["odata_version"] = meta.OdataVersion;
                outD["entity_sets"] = meta.EntitySets.Keys.Order(StringComparer.Ordinal).ToList();
                outD["comparison"] = meta.CompareWithExpected();
            }
            return outD;
        }
        if (entity is null || !Entities.Known.ContainsKey(entity)) throw new InputException("Entidad no autorizada para diagnóstico");
        var since = DateTimeOffset.UtcNow - DiagWindows[entity];
        var r = await ctx.ExecuteAsync(new QuerySpec(entity, [new Filter(Entities.DateField[entity], "ge", since)], top: 1), ct);
        return new Dictionary<string, object?>
        {
            ["result"] = r.ToStatusDict(),
            ["note"] = $"Consulta mínima: {Entities.DateField[entity]} >= {TimeParse.Iso(since)} con $top=1. " +
                       "Un resultado EMPTY indica conectividad correcta sin registros en la ventana.",
        };
    }

    public async Task<object> DiagnosticsTextAsync(JsonObject body, CancellationToken ct)
    {
        var d = (Dictionary<string, object?>)await DiagnosticsAsync(body, ct);
        var cred = d["credential_configured"] switch { true => "configurada", false => "no configurada", _ => "n/a" };
        var lines = new List<string>
        {
            "GPV SMT Quality Intelligence - Diagnóstico OData",
            $"Timestamp: {TimeParse.NowUtcIso()}", $"Versión: {d["version"]}", $"Modo: {d["mode"]}", $"Servidor: {d["host"]}",
            $"Puerto: {d["port"]}", $"Esquema: {d["scheme"]}", $"Autenticación: {d["auth_method"]} ({cred})",
            $"Timeout: {Json.Num((double)d["timeout_seconds"]!)} s | Reintentos: {d["max_retries"]} | Concurrencia: {d["max_concurrent_requests"]}",
            $"Bloqueo de política: {d["policy_block"] ?? "ninguno"}", "", "Salud por entidad:",
        };
        foreach (var h in (List<Dictionary<string, object?>>)d["health"]!)
            lines.Add($"  {h["entity"]}: {h["last_status"]} HTTP={h["last_http"] ?? "None"} {h["last_elapsed_ms"]} ms | último OK={h["last_success_at"] ?? "None"} | " +
                      $"último error={h["last_error_at"] ?? "None"} {h["last_error"]} | fallos consecutivos={h["consecutive_failures"]}");
        lines.Add("");
        lines.Add("Últimas consultas:");
        foreach (var q in ((List<Dictionary<string, object?>>)d["recent_queries"]!).Take(10))
            lines.Add($"  {q["ts"]} {q["entity"]} {q["status"]} HTTP={q["http_status"] ?? "None"} {q["elapsed_ms"]} ms intentos={q["attempts"]} filas={q["rows"]} {q["error"]}");
        lines.Add($"Runtime: {d["python"]} | {d["platform"]}");
        return new Dictionary<string, object?> { ["text"] = string.Join("\n", lines) };
    }

    public Task<object> OpenLogsAsync(JsonObject _, CancellationToken ct)
    {
        var path = ctx.Config.ResolvePath("logs");
        if (OperatingSystem.IsWindows())
        {
            Process.Start(new ProcessStartInfo("explorer.exe", $"\"{path}\"") { UseShellExecute = true });
            return Task.FromResult<object>(new Dictionary<string, object?> { ["opened"] = true, ["path"] = path });
        }
        return Task.FromResult<object>(new Dictionary<string, object?> { ["opened"] = false, ["path"] = path });
    }
}
