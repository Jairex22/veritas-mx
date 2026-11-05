using System.Text.Json.Nodes;
using Gpv.Sqi.Analytics;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;

namespace Gpv.Sqi.Services;

/// <summary>Módulo A — Trazabilidad de unidad (SMT + Quality + QualityHistory).</summary>
public sealed class TraceabilityService(AppServices ctx)
{
    /// <summary>Ante error, usa la última lectura válida de la caché marcándola como desactualizada.</summary>
    public static QueryResult WithCacheFallback(QueryResult result, (List<JsonObject> Rows, string? CachedAt) cached)
    {
        if (result.Ok || cached.Rows.Count == 0) return result;
        result.Rows = cached.Rows;
        result.Stale = true;
        result.CachedAt = cached.CachedAt;
        return result;
    }

    public async Task<Dictionary<string, object?>> TraceAsync(string identifier, CancellationToken ct = default)
    {
        var cfg = ctx.Config; var ds = ctx.DataSource;
        // Sin $orderby: el orden se hace localmente (evita trabajo de ordenamiento en FactoryLogix).
        var smt = await ctx.ExecuteAsync(new QuerySpec("SMT", [new Filter("Identifier", "eq", identifier)], top: cfg.Int("trace.max_smt_events")), ct);
        if (smt.Ok) ctx.Cache.Store("SMT", smt.Rows, ds);
        else smt = WithCacheFallback(smt, ctx.Cache.SmtByIdentifier(identifier, ds));
        smt.Rows = smt.Rows.OrderBy(r => TimeParse.SortKey(r.Str("EventDate"))).ToList();

        var quality = await ctx.ExecuteAsync(new QuerySpec("Quality", [new Filter("Identifier", "eq", identifier)], top: cfg.Int("trace.max_quality_rows")), ct);
        if (quality.Ok) ctx.Cache.Store("Quality", quality.Rows, ds);
        else quality = WithCacheFallback(quality, ctx.Cache.QualityByIdentifier(identifier, ds));

        var defectIds = quality.Rows.Select(r => r.Str("DefectID")).Where(d => !Json.IsBlank(d)).Select(d => d!)
            .Distinct().OrderBy(d => d.ToLowerInvariant(), StringComparer.Ordinal).ToList();
        var history = await HistoryAsync(defectIds, cfg.Int("trace.max_history_rows"), ct);

        var sources = new Dictionary<string, Dictionary<string, object?>>
        {
            ["SMT"] = smt.ToStatusDict(), ["Quality"] = quality.ToStatusDict(), ["QualityHistory"] = history.ToStatusDict(),
        };
        var historyAvailable = history.Ok || (history.Stale && history.Rows.Count > 0);
        var defects = Defects.Group(quality.Rows, history.Rows, historyAvailable || defectIds.Count == 0);
        var keywords = cfg.StrList("rework.repair_keywords");
        var alerts = ReworkRules.Evaluate(identifier, smt.Rows, defects, keywords, cfg.ProcessFlows());
        var evidence = Evidence.Classify(identifier, smt.Rows, defects, alerts, sources, keywords);
        var timeline = Timeline.Build(smt.Rows, quality.Rows, history.Rows);
        var header = Header(identifier, smt.Rows, quality.Rows);

        var opsCount = new Dictionary<string, int>();
        foreach (var r in smt.Rows)
        {
            var op = Json.IsBlank(r.Str("OperationName")) ? "(sin nombre)" : r.Str("OperationName")!;
            opsCount[op] = opsCount.GetValueOrDefault(op) + 1;
        }
        var allFailed = !sources.Values.Where(s => (string)s["status"]! != "NOT_REQUESTED").Any(s => (bool)s["ok"]! || (bool)s["stale"]!);
        var found = smt.Rows.Count > 0 || quality.Rows.Count > 0;
        var result = new Dictionary<string, object?>
        {
            ["identifier"] = identifier,
            ["generated_at"] = TimeParse.NowUtcIso(),
            ["data_source"] = ds,
            ["is_demo"] = ds == "demo",
            ["state"] = allFailed ? "ERROR" : found ? "FOUND" : "NOT_FOUND",
            ["header"] = header,
            ["sources"] = sources,
            ["summary"] = new Dictionary<string, object?>
            {
                ["smt_events"] = smt.Rows.Count,
                ["operations"] = opsCount.Select(kv => new Dictionary<string, object?> { ["operation"] = kv.Key, ["count"] = kv.Value }).ToList(),
                ["unique_defects"] = defects.Count,
                ["history_entries"] = history.Rows.Count,
                ["repeated_operations"] = opsCount.Where(kv => kv.Value > 1).Select(kv => kv.Key).ToList(),
                ["final_result"] = evidence["final_result"],
            },
            ["timeline"] = timeline,
            ["defects"] = defects,
            ["alerts"] = alerts,
            ["evidence"] = evidence,
            ["disclaimer"] = Evidence.ClosureDisclaimer,
            ["smt_events"] = smt.Rows,
        };
        ctx.Audit.AddSearch(ds, "trace", identifier, $"{smt.Rows.Count} eventos, {defects.Count} defectos, estado {result["state"]}");
        ctx.Audit.SaveAnalysis(ds, "trace", identifier, result);
        return result;
    }

    private async Task<QueryResult> HistoryAsync(List<string> defectIds, int top, CancellationToken ct)
    {
        var ds = ctx.DataSource;
        if (defectIds.Count == 0)
            return new QueryResult(ODataStatus.NOT_REQUESTED, "QualityHistory")
            { DataSource = ds, QueryDescription = "Sin DefectID asociados: no se consulta QualityHistory" };
        QueryResult? merged = null;
        for (var i = 0; i < defectIds.Count; i += ODataFilterBuilder.MaxInValues)
        {
            var chunk = defectIds.Skip(i).Take(ODataFilterBuilder.MaxInValues).ToList();
            var res = await ctx.ExecuteAsync(new QuerySpec("QualityHistory", [new Filter("DefectID", "in", chunk)], top: top), ct);
            if (merged is null) merged = res;
            else
            {
                merged.ElapsedMs += res.ElapsedMs;
                merged.Attempts += res.Attempts;
                if (res.Ok) merged.Rows.AddRange(res.Rows);
                else { merged.Status = res.Status; merged.Error = res.Error; merged.HttpStatus = res.HttpStatus; }
            }
            if (!res.Ok) break;
        }
        if (merged!.Ok)
        {
            merged.Status = merged.Rows.Count > 0 ? ODataStatus.OK : ODataStatus.EMPTY;
            ctx.Cache.Store("QualityHistory", merged.Rows, ds);
            return merged;
        }
        merged.Rows = [];
        return WithCacheFallback(merged, ctx.Cache.HistoryByDefects(defectIds, ds));
    }

    private static Dictionary<string, object?> Header(string identifier, IReadOnlyList<JsonObject> smt, IReadOnlyList<JsonObject> quality)
    {
        static string? First(IReadOnlyList<JsonObject> rows, string key) => rows.Select(r => r.Str(key)).FirstOrDefault(v => !Json.IsBlank(v));
        var lines = quality.Select(r => r.Str("Line")).Where(l => !Json.IsBlank(l)).Select(l => l!).Distinct().Order(StringComparer.Ordinal).ToList();
        return new()
        {
            ["identifier"] = identifier,
            ["customer"] = First(smt, "Customer") ?? First(quality, "CustomerName"),
            ["assembly"] = First(smt, "Assembly") ?? First(quality, "Assembly"),
            ["assembly_revision"] = First(smt, "AssemblyRevision") ?? First(quality, "AssemblyRevision"),
            ["batch"] = First(smt, "Batch") ?? First(quality, "BatchName"),
            ["work_order"] = First(smt, "WorkOrder") ?? First(quality, "WorkOrder"),
            ["lot"] = First(quality, "Lot"),
            ["lines_registered_in_defects"] = lines,
            ["line_verified"] = false,
            ["line_note"] = lines.Count > 0
                ? "Línea registrada únicamente en defectos de Quality; no verificada para todas las operaciones."
                : "No verificable: la entidad SMT no expone la línea.",
        };
    }
}
