using System.Text.Json.Nodes;
using Gpv.Sqi.Analytics;
using Gpv.Sqi.Api;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;

namespace Gpv.Sqi.Services;

/// <summary>Módulo B — SMT Production Pulse. No calcula PASS/FAIL ni tarjetas buenas.</summary>
public sealed class PulseService(AppServices ctx)
{
    private static readonly (string Key, string Field)[] FilterMap =
        [("customer", "Customer"), ("assembly", "Assembly"), ("batch", "Batch"), ("operation", "OperationName")];

    public static List<Dictionary<string, object?>> CountBy(IEnumerable<JsonObject> rows, string field)
    {
        var acc = new Dictionary<string, int>();
        foreach (var r in rows)
        {
            var k = Json.IsBlank(r.Str(field)) ? "(vacío)" : r.Str(field)!;
            acc[k] = acc.GetValueOrDefault(k) + 1;
        }
        return acc.OrderBy(kv => -kv.Value).ThenBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => new Dictionary<string, object?> { ["key"] = kv.Key, ["count"] = kv.Value }).ToList();
    }

    public async Task<Dictionary<string, object?>> PulseAsync(JsonObject p, CancellationToken ct = default)
    {
        var cfg = ctx.Config; var ds = ctx.DataSource;
        var (start, end, label) = TimeWindows.Resolve(p, cfg);
        var filters = new List<Filter> { new("EventDate", "ge", start), new("EventDate", "le", end) };
        var applied = new Dictionary<string, object?>();
        foreach (var (key, field) in FilterMap)
        {
            var val = InputValidation.Term(p, key, key);
            if (val is null) continue;
            filters.Add(new Filter(field, "eq", val));
            applied[key] = val;
        }
        var maxEvents = cfg.Int("pulse.max_events");
        var res = await ctx.ExecuteAsync(new QuerySpec("SMT", filters, [("EventDate", "desc")], maxEvents), ct);
        List<JsonObject> rows;
        if (res.Ok) { ctx.Cache.Store("SMT", res.Rows, ds); rows = res.Rows; }
        else
        {
            var (cached, cachedAt) = ctx.Cache.SmtInWindow(start, end, ds, maxEvents);
            rows = cached.Where(r => applied.All(kv => r.Str(FilterMap.First(f => f.Key == kv.Key).Field) == (string?)kv.Value)).ToList();
            if (rows.Count > 0) { res.Stale = true; res.CachedAt = cachedAt; }
        }
        var keywords = cfg.StrList("rework.repair_keywords");
        var identOps = new Dictionary<(string?, string?), int>();
        foreach (var r in rows)
        {
            var k = (r.Str("Identifier"), r.Str("OperationName"));
            identOps[k] = identOps.GetValueOrDefault(k) + 1;
        }
        var repeated = identOps.Where(kv => kv.Value > 1 && !Json.IsBlank(kv.Key.Item1)).Select(kv => kv.Key.Item1!)
            .Distinct().Order(StringComparer.Ordinal).ToList();
        var last = rows.Select(r => (Row: r, T: TimeParse.Parse(r.Str("EventDate")))).Where(x => x.T is { HasOffset: true })
            .OrderByDescending(x => x.T!.Value.Value).Select(x => x.Row).FirstOrDefault();
        static int Distinct(List<JsonObject> rows, string f) => rows.Select(r => r.Str(f)).Where(v => !Json.IsBlank(v)).Distinct().Count();
        var kpis = new Dictionary<string, object?>
        {
            ["events"] = rows.Count,
            ["unique_identifiers"] = Distinct(rows, "Identifier"),
            ["assemblies"] = Distinct(rows, "Assembly"),
            ["batches"] = Distinct(rows, "Batch"),
            ["operations"] = Distinct(rows, "OperationName"),
            ["last_event"] = last?.Str("EventDate"),
            ["repeated_identifiers"] = repeated.Count,
            ["repair_events"] = rows.Count(r => ReworkRules.IsRepair(r.Str("OperationName"), keywords)),
            ["response_ms"] = Math.Round(res.ElapsedMs, 1),
        };
        var notes = new List<string>
        {
            "Los eventos no equivalen a tarjetas producidas ni a unidades aprobadas.",
            "Attempts y Placements no se interpretan como tarjetas producidas.",
            "La entidad SMT puede incluir operaciones de otras áreas (p. ej. FCT).",
        };
        if (res.Truncated) notes.Add("Resultado truncado al límite configurado de eventos.");
        var result = new Dictionary<string, object?>
        {
            ["data_source"] = ds, ["is_demo"] = ds == "demo",
            ["window"] = TimeWindows.Describe(start, end, label, cfg),
            ["filters"] = applied,
            ["source"] = res.ToStatusDict(),
            ["kpis"] = kpis,
            ["by_customer"] = CountBy(rows, "Customer"),
            ["by_assembly"] = CountBy(rows, "Assembly"),
            ["by_batch"] = CountBy(rows, "Batch"),
            ["by_operation"] = CountBy(rows, "OperationName"),
            ["repeated_identifiers"] = repeated.Take(100).ToList(),
            ["events"] = rows.Take(maxEvents).ToList(),
            ["line_filter"] = new Dictionary<string, object?> { ["available"] = false, ["reason"] = "La entidad SMT no expone Line; no existe relación comprobable." },
            ["notes"] = notes,
            ["generated_at"] = TimeParse.NowUtcIso(),
        };
        ctx.Audit.AddSearch(ds, "pulse", label, $"{kpis["events"]} eventos");
        return result;
    }
}
