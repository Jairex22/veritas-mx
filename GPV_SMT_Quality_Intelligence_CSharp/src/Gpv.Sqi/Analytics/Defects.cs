using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.Analytics;

/// <summary>
/// Agrupación de defectos por DefectID. Un defecto = un DefectID único; las filas de QualityHistory nunca
/// cuentan como defectos. Closed no significa PASS; vacío tampoco. Estados no estándar ("False") no se interpretan.
/// </summary>
public static class Defects
{
    private static readonly HashSet<string> KnownHistoryStatuses = ["open", "closed"];

    private static string Key(string? defectId) => (defectId ?? "").Trim().ToLowerInvariant();

    public static List<Dictionary<string, object?>> Group(IReadOnlyList<JsonObject> quality, IReadOnlyList<JsonObject> history, bool historyAvailable)
    {
        var byId = new Dictionary<string, (string? DefectId, int QualityRows, JsonObject Record)>();
        var order = new List<string>();
        foreach (var r in quality)
        {
            var k = Key(r.Str("DefectID"));
            if (k.Length == 0) k = $"sin-id:{byId.Count}";
            if (byId.TryGetValue(k, out var e)) byId[k] = (e.DefectId, e.QualityRows + 1, e.Record);
            else { byId[k] = (r.Str("DefectID"), 1, r); order.Add(k); }
        }
        var hist = new Dictionary<string, List<JsonObject>>();
        foreach (var h in history)
        {
            var k = Key(h.Str("DefectID"));
            if (!hist.TryGetValue(k, out var l)) hist[k] = l = [];
            l.Add(h);
        }

        var outList = new List<Dictionary<string, object?>>();
        foreach (var k in order)
        {
            var (defectId, qualityRows, r) = byId[k];
            var entries = hist.GetValueOrDefault(k, []).OrderBy(h => TimeParse.SortKey(h.Str("DefectHistoryTime"))).ToList();
            var status = (r.Str("DefectStatus") ?? "").Trim();
            var closedEntries = entries.Where(h => Json.PyStr(h.Str("DefectHistoryStatus")).Equals("closed", StringComparison.OrdinalIgnoreCase)).ToList();
            var uninterpreted = entries.Select(h => Json.PyStr(h.Str("DefectHistoryStatus")))
                .Where(s => !KnownHistoryStatuses.Contains(s.ToLowerInvariant())).Distinct().Order(StringComparer.Ordinal).ToList();
            var created = TimeParse.Parse(r.Str("DateCreated"));
            if (created is null && entries.Count > 0) created = TimeParse.Parse(entries[0].Str("DefectHistoryTime"));
            var closedAt = closedEntries.Count > 0 ? TimeParse.Parse(closedEntries[^1].Str("DefectHistoryTime")) : null;
            double? ttc = null;
            if (created is { HasOffset: true } c && closedAt is { HasOffset: true } ca && ca.Value >= c.Value)
                ttc = Math.Round((ca.Value - c.Value).TotalSeconds / 60, 2);

            var notes = new List<string>();
            string classification;
            if (status.Equals("open", StringComparison.OrdinalIgnoreCase)) classification = "ACTIVE";
            else if (status.Equals("closed", StringComparison.OrdinalIgnoreCase))
            {
                classification = "CLOSED";
                if (historyAvailable && closedEntries.Count == 0)
                {
                    classification = "HISTORY_INCOMPLETE";
                    notes.Add("Estado Closed sin registro histórico de cierre");
                }
            }
            else
            {
                classification = "UNKNOWN_STATUS";
                notes.Add($"Estado de defecto no reconocido: {(status.Length > 0 ? status : "(vacío)")}");
            }
            if (!historyAvailable)
            {
                notes.Add("QualityHistory no disponible: historial no verificable");
                if (classification == "CLOSED") classification = "HISTORY_INCOMPLETE";
            }
            if (uninterpreted.Count > 0) notes.Add("Estados históricos no interpretados: " + string.Join(", ", uninterpreted));
            if (qualityRows > 1) notes.Add($"{qualityRows} filas de Quality para el mismo DefectID (contado una vez)");

            var last = closedEntries.Count > 0 ? closedEntries[^1] : null;
            string? First(params string[] keys) => keys.Select(r.Str).FirstOrDefault(x => !Json.IsBlank(x));
            outList.Add(new()
            {
                ["defect_id"] = defectId,
                ["status"] = status.Length > 0 ? status : null,
                ["classification"] = classification,
                ["description"] = First("AegisInspectionCodeName", "SymptomDescription"),
                ["category"] = First("AegisCategoryName", "SymptomCategory"),
                ["comment"] = r.Str("DefectComment"),
                ["reference"] = r.Str("DefectReference"),
                ["part_number"] = r.Str("DefectPartNumber"),
                ["source_operation"] = r.Str("SourceOperation"),
                ["current_operation"] = r.Str("CurrentOperation"),
                ["inspection_workstation"] = r.Str("InspectionWorkstation"),
                ["line_registered"] = r.Str("Line"),
                ["identifier"] = r.Str("Identifier"),
                ["assembly"] = r.Str("Assembly"),
                ["batch"] = r.Str("BatchName"),
                ["lot"] = r.Str("Lot"),
                ["date_created"] = r.Str("DateCreated"),
                ["closed_at"] = last?.Str("DefectHistoryTime"),
                ["closed_operation"] = last?.Str("DefectHistoryOperation"),
                ["closed_workstation"] = last?.Str("DefectHistoryWorkstation"),
                ["closed_operator"] = last?.Str("DefectHistoryOperator"),
                ["time_to_close_min"] = ttc,
                ["history_entries"] = entries.Count,
                ["history"] = entries,
                ["notes"] = notes,
            });
        }
        return outList.OrderBy(d => TimeParse.SortKey((string?)d["date_created"])).ToList();
    }

    public static Dictionary<string, object?> Summarize(IReadOnlyList<Dictionary<string, object?>> defects)
    {
        List<Dictionary<string, object?>> CountBy(string field)
        {
            var acc = new Dictionary<string, int>();
            foreach (var d in defects)
            {
                var k = d[field] as string;
                if (string.IsNullOrEmpty(k)) k = "(no registrado)";
                acc[k] = acc.GetValueOrDefault(k) + 1;
            }
            return acc.OrderBy(kv => -kv.Value).ThenBy(kv => kv.Key, StringComparer.Ordinal)
                .Select(kv => new Dictionary<string, object?> { ["key"] = kv.Key, ["count"] = kv.Value }).ToList();
        }
        int Count(string cls) => defects.Count(d => (string?)d["classification"] == cls);
        var ttcs = defects.Select(d => d["time_to_close_min"] as double?).Where(x => x.HasValue).Select(x => x!.Value).ToList();
        return new()
        {
            ["unique_defects"] = defects.Count,
            ["active"] = Count("ACTIVE"),
            ["closed"] = Count("CLOSED"),
            ["history_incomplete"] = Count("HISTORY_INCOMPLETE"),
            ["unknown_status"] = Count("UNKNOWN_STATUS"),
            ["by_status"] = CountBy("status"),
            ["by_assembly"] = CountBy("assembly"),
            ["by_batch"] = CountBy("batch"),
            ["by_operation"] = CountBy("source_operation"),
            ["by_line"] = CountBy("line_registered"),
            ["by_reference"] = CountBy("reference"),
            ["by_category"] = CountBy("category"),
            ["by_description"] = CountBy("description"),
            ["avg_time_to_close_min"] = ttcs.Count > 0 ? Math.Round(ttcs.Average(), 2) : null,
            ["time_to_close_samples"] = ttcs.Count,
        };
    }
}
