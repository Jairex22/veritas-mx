using System.Text.Json.Nodes;
using Gpv.Sqi.Analytics;
using Gpv.Sqi.Api;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;

namespace Gpv.Sqi.Services;

/// <summary>Módulo D — Rework &amp; Loop Detector.</summary>
public sealed class ReworkService(AppServices ctx)
{
    public async Task<Dictionary<string, object?>> ByIdentifierAsync(string identifier, CancellationToken ct = default)
    {
        var trace = await new TraceabilityService(ctx).TraceAsync(identifier, ct);
        var summary = (Dictionary<string, object?>)trace["summary"]!;
        return new()
        {
            ["mode"] = "identifier", ["data_source"] = trace["data_source"], ["is_demo"] = trace["is_demo"], ["identifier"] = identifier,
            ["sources"] = trace["sources"], ["alerts"] = trace["alerts"], ["rules"] = ReworkRules.PublicRules(),
            ["units"] = new List<object> { new Dictionary<string, object?> { ["identifier"] = identifier, ["events"] = summary["smt_events"], ["alerts"] = trace["alerts"] } },
        };
    }

    public async Task<Dictionary<string, object?>> ByBatchAsync(JsonObject body, CancellationToken ct = default)
    {
        var batch = InputValidation.Term(body, "batch", "Batch", required: true)!;
        var cfg = ctx.Config; var ds = ctx.DataSource;
        var res = await ctx.ExecuteAsync(new QuerySpec("SMT", [new Filter("Batch", "eq", batch)], top: cfg.Int("rework.max_batch_events")), ct);
        if (res.Ok) ctx.Cache.Store("SMT", res.Rows, ds);
        var groups = new SortedDictionary<string, List<JsonObject>>(StringComparer.Ordinal);
        foreach (var r in res.Rows)
        {
            var id = Json.IsBlank(r.Str("Identifier")) ? "(sin Identifier)" : r.Str("Identifier")!;
            if (!groups.TryGetValue(id, out var l)) groups[id] = l = [];
            l.Add(r);
        }
        var units = new List<object>();
        foreach (var (ident, rows) in groups)
        {
            var alerts = ReworkRules.Evaluate(ident, rows, [], cfg.StrList("rework.repair_keywords"), cfg.ProcessFlows());
            if (alerts.Count > 0) units.Add(new Dictionary<string, object?> { ["identifier"] = ident, ["events"] = rows.Count, ["alerts"] = alerts });
        }
        ctx.Audit.AddSearch(ds, "rework", batch, $"{units.Count} unidades con alertas");
        var notes = new List<string> { "Análisis por batch usa solo la entidad SMT; los defectos se consultan en la vista por unidad." };
        if (res.Truncated) notes.Add("Resultado truncado al límite configurado de eventos.");
        return new()
        {
            ["mode"] = "batch", ["data_source"] = ds, ["is_demo"] = ds == "demo", ["batch"] = batch, ["source"] = res.ToStatusDict(),
            ["units_observed"] = groups.Count, ["units"] = units, ["rules"] = ReworkRules.PublicRules(), ["notes"] = notes,
            ["generated_at"] = TimeParse.NowUtcIso(),
        };
    }
}
