using System.Text.Json.Nodes;
using Gpv.Sqi.Analytics;
using Gpv.Sqi.Config;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.Reports;

public sealed record ReportSection(string Name, List<List<object?>> Rows);

public sealed record UnitReport(string Title, string Identifier, bool IsDemo, string Disclaimer, List<ReportSection> Sections);

/// <summary>Reporte de unidad a partir del análisis de trazabilidad (secciones neutrales al formato).</summary>
public static class ReportBuilder
{
    private static string? S(JsonNode? n) => n is JsonValue v ? (v.TryGetValue<string>(out var s) ? s : v.ToJsonString()) : null;
    private static object? V(JsonNode? n)
    {
        if (n is not JsonValue v) return null;
        if (v.TryGetValue<string>(out var s)) return s;
        if (v.TryGetValue<bool>(out var b)) return b;
        if (v.TryGetValue<double>(out var d)) return d;
        return v.ToJsonString();
    }
    private static string Or(string? v, string fallback) => string.IsNullOrEmpty(v) ? fallback : v;
    private static IEnumerable<JsonObject> Objs(JsonNode? n) => n is JsonArray a ? a.OfType<JsonObject>() : [];
    private static IEnumerable<string> Strs(JsonNode? n) => n is JsonArray a ? a.Select(x => S(x) ?? "") : [];

    public static UnitReport Build(JsonObject trace)
    {
        var h = trace["header"]!.AsObject();
        var demo = trace["is_demo"]?.GetValue<bool>() == true;
        var finalResult = S(trace["summary"]?["final_result"]);
        var lines = string.Join(", ", Strs(h["lines_registered_in_defects"]));
        var general = new List<List<object?>>
        {
            new() { "Reporte", "GPV SMT Quality Intelligence - Reporte de unidad" },
            new() { "Fecha de generación", TimeParse.NowUtcIso() },
            new() { "Análisis realizado", S(trace["generated_at"]) },
            new() { "Versión", AppConfig.AppVersion },
            new() { "Fuente de datos", demo ? "DEMOSTRACIÓN (no producción)" : "FactoryLogix OData" },
            new() { "Cliente", Or(S(h["customer"]), "No verificable") },
            new() { "Assembly", Or(S(h["assembly"]), "No verificable") },
            new() { "Revisión", Or(S(h["assembly_revision"]), "No verificable") },
            new() { "Batch", Or(S(h["batch"]), "No verificable") },
            new() { "Lot", Or(S(h["lot"]), "No verificable") },
            new() { "Identifier", S(trace["identifier"]) },
            new() { "Línea", Or(lines, "No verificable") },
            new() { "Nota de línea", S(h["line_note"]) },
            new() { "Resultado final", finalResult == Evidence.FinalResultNotVerifiable ? "NO VERIFICABLE (no existe evidencia de aprobación final)" : finalResult },
        };
        var sources = new List<List<object?>> { new() { "Fuente", "Estado", "HTTP", "Tiempo (ms)", "Registros", "Desactualizado", "Error" } };
        foreach (var (k, node) in trace["sources"]!.AsObject())
        {
            var v = node!.AsObject();
            sources.Add([k, S(v["status"]), V(v["http_status"]) ?? "", V(v["elapsed_ms"]), V(v["rows"]),
                v["stale"]?.GetValue<bool>() == true ? "Sí" : "No", S(v["error"]) ?? ""]);
        }
        var events = new List<List<object?>> { new() { "Fecha", "Operación", "Batch", "Assembly", "WorkOrder" } };
        events.AddRange(Objs(trace["smt_events"]).Select(r => new List<object?> { r.Str("EventDate"), r.Str("OperationName"), r.Str("Batch"), r.Str("Assembly"), r.Str("WorkOrder") }));
        var defects = new List<List<object?>> { new() { "DefectID", "Descripción", "Comentario", "Referencia", "Estado", "Clasificación", "Operación origen",
            "Estación inspección", "Línea registrada", "Creado", "Cerrado", "Min. a cierre", "Notas" } };
        var history = new List<List<object?>> { new() { "DefectID", "Hora", "Estado histórico", "Operación", "Estación", "Operador", "Comentario" } };
        foreach (var d in Objs(trace["defects"]))
        {
            defects.Add([S(d["defect_id"]), S(d["description"]), S(d["comment"]), S(d["reference"]), S(d["status"]), S(d["classification"]),
                S(d["source_operation"]), S(d["inspection_workstation"]), S(d["line_registered"]), S(d["date_created"]), S(d["closed_at"]),
                V(d["time_to_close_min"]), string.Join("; ", Strs(d["notes"]))]);
            foreach (var e in Objs(d["history"]))
                history.Add([e.Str("DefectID"), e.Str("DefectHistoryTime"), e.Str("DefectHistoryStatus"), e.Str("DefectHistoryOperation"),
                    e.Str("DefectHistoryWorkstation"), e.Str("DefectHistoryOperator"), e.Str("DefectHistoryComment")]);
        }
        var rework = new List<List<object?>> { new() { "Regla", "Categoría", "Confianza", "Explicación", "Evidencia", "No se puede concluir" } };
        rework.AddRange(Objs(trace["alerts"]).Select(a => new List<object?> { S(a["rule"]), S(a["title"]), S(a["confidence"]), S(a["explanation"]),
            string.Join(", ", Strs(a["evidence"])), string.Join("; ", Strs(a["cannot_conclude"])) }));
        var ev = trace["evidence"]!.AsObject();
        var evidence = new List<List<object?>> { new() { "Tipo", "Descripción" } };
        evidence.AddRange(Strs(ev["confirmed"]).Select(x => new List<object?> { "Evidencia confirmada", x }));
        evidence.AddRange(Strs(ev["inferred"]).Select(x => new List<object?> { "Hipótesis / inferencia", x }));
        evidence.AddRange(Strs(ev["unverifiable"]).Select(x => new List<object?> { "Pendiente de verificar", x }));

        return new UnitReport($"Reporte de unidad {S(trace["identifier"])}", S(trace["identifier"])!, demo, Evidence.ClosureDisclaimer,
        [
            new("General", general), new("Fuentes OData", sources), new("Eventos de proceso", events), new("Defectos", defects),
            new("Historial de calidad", history), new("Posibles reprocesos", rework), new("Evidencia", evidence),
        ]);
    }
}
