using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.Analytics;

/// <summary>Fusión cronológica de eventos SMT, creación de defectos e historial de calidad.</summary>
public static class Timeline
{
    private static Dictionary<string, object?> Details(JsonObject r, params string[] keys) =>
        keys.Where(k => !Json.IsBlank(r.Str(k))).ToDictionary(k => k, k => (object?)r[k]?.DeepClone());

    public static List<Dictionary<string, object?>> Build(IReadOnlyList<JsonObject> smt, IReadOnlyList<JsonObject> quality, IReadOnlyList<JsonObject> history)
    {
        var items = new List<Dictionary<string, object?>>();
        for (var i = 0; i < smt.Count; i++)
        {
            var r = smt[i];
            items.Add(new()
            {
                ["kind"] = "SMT_EVENT", ["source"] = "SMT", ["ref"] = $"SMT#{i + 1}", ["time"] = r.Str("EventDate"),
                ["title"] = Json.IsBlank(r.Str("OperationName")) ? "(operación sin nombre)" : r.Str("OperationName"),
                ["details"] = Details(r, "Batch", "Assembly", "AssemblyRevision", "WorkOrder", "Process", "Attempts", "Placements"),
            });
        }
        var seen = new HashSet<string>();
        foreach (var r in quality)
        {
            var did = (r.Str("DefectID") ?? "").ToLowerInvariant();
            if (!seen.Add(did)) continue;
            var desc = new[] { r.Str("AegisInspectionCodeName"), r.Str("SymptomDescription"), r.Str("DefectComment") }
                .FirstOrDefault(x => !Json.IsBlank(x)) ?? "sin descripción";
            items.Add(new()
            {
                ["kind"] = "DEFECT_CREATED", ["source"] = "Quality", ["ref"] = $"DEF:{Json.PyStr(r.Str("DefectID"))}",
                ["time"] = r.Str("DateCreated"), ["title"] = $"Defecto registrado: {desc}",
                ["details"] = Details(r, "DefectID", "DefectStatus", "SourceOperation", "InspectionWorkstation", "Line", "DefectReference", "DefectComment"),
            });
        }
        for (var i = 0; i < history.Count; i++)
        {
            var r = history[i];
            items.Add(new()
            {
                ["kind"] = "DEFECT_HISTORY", ["source"] = "QualityHistory", ["ref"] = $"QH#{i + 1}", ["time"] = r.Str("DefectHistoryTime"),
                ["title"] = $"Historial de defecto: estado {Json.PyStr(r.Str("DefectHistoryStatus"))}",
                ["details"] = Details(r, "DefectID", "DefectHistoryOperation", "DefectHistoryWorkstation", "DefectHistoryOperator", "DefectHistoryComment"),
            });
        }
        var kindOrder = new Dictionary<string, int> { ["SMT_EVENT"] = 0, ["DEFECT_CREATED"] = 1, ["DEFECT_HISTORY"] = 2 };
        foreach (var it in items)
        {
            var t = TimeParse.Parse((string?)it["time"]);
            it["time_verified"] = t is { HasOffset: true };
        }
        return items.OrderBy(it => TimeParse.SortKey((string?)it["time"])).ThenBy(it => kindOrder[(string)it["kind"]!]).ToList();
    }
}
