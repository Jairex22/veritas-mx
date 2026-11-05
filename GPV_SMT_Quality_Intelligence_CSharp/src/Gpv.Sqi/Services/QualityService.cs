using System.Text.Json.Nodes;
using Gpv.Sqi.Analytics;
using Gpv.Sqi.Api;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;

namespace Gpv.Sqi.Services;

/// <summary>Módulo C — Quality Intelligence (defectos únicos por DefectID).</summary>
public sealed class QualityService(AppServices ctx)
{
    private static readonly (string Key, string Field)[] FilterMap =
        [("assembly", "Assembly"), ("batch", "BatchName"), ("status", "DefectStatus"), ("line", "Line"), ("customer", "CustomerName"), ("operation", "SourceOperation")];

    private static List<Dictionary<string, object?>> WithoutHistory(IEnumerable<Dictionary<string, object?>> defects) =>
        defects.Select(d => d.Where(kv => kv.Key != "history").ToDictionary(kv => kv.Key, kv => kv.Value)).ToList();

    public async Task<Dictionary<string, object?>> DashboardAsync(JsonObject p, CancellationToken ct = default)
    {
        var cfg = ctx.Config; var ds = ctx.DataSource;
        if (!p.ContainsKey("window") || p["window"] is null) { p = p.Clone(); p["window"] = "24h"; }
        var (start, end, label) = TimeWindows.Resolve(p, cfg);
        var filters = new List<Filter> { new("DateCreated", "ge", start), new("DateCreated", "le", end) };
        var applied = new Dictionary<string, object?>();
        foreach (var (key, field) in FilterMap)
        {
            var val = InputValidation.Term(p, key, key);
            if (val is null) continue;
            filters.Add(new Filter(field, "eq", val));
            applied[key] = val;
        }
        var max = cfg.Int("quality.max_defects");
        var res = await ctx.ExecuteAsync(new QuerySpec("Quality", filters, [("DateCreated", "desc")], max), ct);
        var rows = res.Rows;
        if (res.Ok) ctx.Cache.Store("Quality", rows, ds);
        else
        {
            var (cached, cachedAt) = ctx.Cache.QualityInWindow(start, end, ds, max);
            rows = cached.Where(r => applied.All(kv => r.Str(FilterMap.First(f => f.Key == kv.Key).Field) == (string?)kv.Value)).ToList();
            if (rows.Count > 0) { res.Stale = true; res.CachedAt = cachedAt; }
        }
        // En el dashboard no se consulta QualityHistory automáticamente (carga).
        var defects = Defects.Group(rows, [], historyAvailable: true);
        foreach (var d in defects)
        {
            if ((string?)d["classification"] == "HISTORY_INCOMPLETE") d["classification"] = "CLOSED";
            var notes = ((List<string>)d["notes"]!).Where(n => !n.Contains("sin registro histórico")).ToList();
            notes.Add("Historial no consultado en el dashboard (use 'Calcular tiempos de cierre')");
            d["notes"] = notes;
        }
        var summary = Defects.Summarize(defects);
        var resultNotes = new List<string>
        {
            "Los defectos se cuentan por DefectID único.",
            "Un defecto Closed no significa que la unidad esté aprobada.",
            "BatchQuantity y CompletedQuantity no se usan como unidades aprobadas.",
        };
        if (res.Truncated) resultNotes.Add("Resultado truncado al límite configurado.");
        ctx.Audit.AddSearch(ds, "quality", label, $"{summary["unique_defects"]} defectos únicos");
        return new()
        {
            ["data_source"] = ds, ["is_demo"] = ds == "demo",
            ["window"] = TimeWindows.Describe(start, end, label, cfg),
            ["filters"] = applied, ["source"] = res.ToStatusDict(),
            ["summary"] = summary,
            ["defects"] = WithoutHistory(defects),
            ["notes"] = resultNotes,
            ["generated_at"] = TimeParse.NowUtcIso(),
        };
    }

    public async Task<Dictionary<string, object?>> CloseTimesAsync(JsonArray defectIds, CancellationToken ct = default)
    {
        var cfg = ctx.Config; var ds = ctx.DataSource;
        var limit = cfg.Int("quality.max_closetime_lookups");
        var ids = defectIds.Select(InputValidation.Guid).Distinct().OrderBy(x => x.ToLowerInvariant(), StringComparer.Ordinal).Take(limit).ToList();
        if (ids.Count == 0) return new() { ["source"] = null, ["defects"] = new List<object>(), ["data_source"] = ds };
        var rows = new List<JsonObject>();
        QueryResult? last = null;
        for (var i = 0; i < ids.Count; i += ODataFilterBuilder.MaxInValues)
        {
            var res = await ctx.ExecuteAsync(new QuerySpec("QualityHistory", [new Filter("DefectID", "in", ids.Skip(i).Take(ODataFilterBuilder.MaxInValues).ToList())],
                [("DefectHistoryTime", "asc")], 500), ct);
            last = res;
            if (!res.Ok) break;
            rows.AddRange(res.Rows);
            ctx.Cache.Store("QualityHistory", res.Rows, ds);
        }
        var qualityRows = new List<JsonObject>();
        foreach (var d in ids)
        {
            var (q, _) = ctx.Cache.QualityByDefect(d, ds);
            qualityRows.Add(q.Count > 0 ? q[0] : new JsonObject { ["DefectID"] = d });
        }
        var ok = last is not null && last.Ok;
        var defects = Defects.Group(qualityRows, rows, historyAvailable: ok);
        return new()
        {
            ["data_source"] = ds, ["source"] = last?.ToStatusDict(), ["defects"] = WithoutHistory(defects), ["limited_to"] = limit,
        };
    }
}
