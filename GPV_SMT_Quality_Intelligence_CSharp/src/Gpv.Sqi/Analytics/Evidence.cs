using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.Analytics;

/// <summary>Clasificación de evidencia: confirmada, inferencias y no verificable.</summary>
public static class Evidence
{
    public const string FinalResultNotVerifiable = "NO_VERIFICABLE";
    public const string ClosureDisclaimer = "El cierre de un defecto no constituye por sí mismo evidencia de aprobación final de la unidad.";

    private static readonly HashSet<string> InferredCategories = ["POSSIBLE_REWORK", "REPEATED_OPERATION", "TIME_ORDER_REVIEW", "LOOP_NOT_CONFIRMABLE"];

    public static Dictionary<string, object?> Classify(string identifier, IReadOnlyList<JsonObject> smt, IReadOnlyList<Dictionary<string, object?>> defects,
        IReadOnlyList<Dictionary<string, object?>> alerts, IReadOnlyDictionary<string, Dictionary<string, object?>> sources, IReadOnlyList<string> repairKeywords)
    {
        var confirmed = new List<string>(); var inferred = new List<string>(); var unverifiable = new List<string>();
        var smtOk = (bool)sources["SMT"]["ok"]!;
        var qOk = (bool)sources["Quality"]["ok"]!;
        var qhStatus = (string)sources["QualityHistory"]["status"]!;

        if (smtOk)
        {
            if (smt.Count > 0)
            {
                var ops = new Dictionary<string, int>();
                foreach (var r in smt)
                {
                    var op = Json.IsBlank(r.Str("OperationName")) ? "(sin nombre)" : r.Str("OperationName")!;
                    ops[op] = ops.GetValueOrDefault(op) + 1;
                }
                foreach (var (op, n) in ops) confirmed.Add($"{n} evento(s) '{op}' registrados en la entidad SMT.");
                var repairs = smt.Count(r => ReworkRules.IsRepair(r.Str("OperationName"), repairKeywords));
                if (repairs > 0) confirmed.Add($"Reparación registrada: {repairs} evento(s) de reparación.");
            }
            else confirmed.Add("La entidad SMT respondió sin eventos para este Identifier.");
        }
        else unverifiable.Add($"Eventos de proceso: la fuente SMT no respondió ({sources["SMT"]["status"]}).");

        if (qOk)
        {
            if (defects.Count > 0)
            {
                foreach (var d in defects)
                {
                    var comment = Json.IsBlank((string?)d["comment"]) ? "sin comentario" : (string)d["comment"]!;
                    confirmed.Add($"Defecto único {(string?)d["description"] ?? ""} ({comment}) DefectID {Json.PyStr((string?)d["defect_id"])} con estado {Json.PyStr((string?)d["status"])}.");
                    if (!Json.IsBlank((string?)d["closed_at"]))
                    {
                        string Part(string key, string label) => Json.IsBlank((string?)d[key]) ? "" : $", {label} {d[key]}";
                        confirmed.Add($"Cierre histórico del defecto en {d["closed_at"]}" + Part("closed_operation", "operación")
                            + Part("closed_workstation", "estación") + Part("closed_operator", "operador") + ".");
                    }
                    if (!Json.IsBlank((string?)d["line_registered"]))
                        unverifiable.Add($"Que todas las operaciones ocurrieran en '{d["line_registered"]}' (la línea está registrada solo en el defecto).");
                }
            }
            else confirmed.Add("Quality respondió sin defectos para este Identifier (no equivale a PASS).");
        }
        else unverifiable.Add($"Defectos: la fuente Quality no respondió ({sources["Quality"]["status"]}).");

        if (qhStatus is not ("OK" or "EMPTY" or "NOT_REQUESTED"))
            unverifiable.Add($"Historial de calidad: QualityHistory no respondió ({qhStatus}).");

        foreach (var a in alerts)
            if (InferredCategories.Contains((string)a["category"]!))
                inferred.Add($"[{a["rule"]} · confianza {a["confidence"]}] {a["title"]}: {a["explanation"]}");

        unverifiable.Add("Resultado final PASS/FAIL de la unidad: ninguna de las entidades SMT, Quality o QualityHistory registra una aprobación final.");
        if (defects.Count > 0)
        {
            unverifiable.Add("Acción física exacta realizada por el técnico de reparación.");
            unverifiable.Add(ClosureDisclaimer);
        }
        if (alerts.Any(a => (string)a["category"]! == "REPEATED_OPERATION"))
            unverifiable.Add("Que eventos repetidos de una operación correspondan a tarjetas diferentes (son del mismo Identifier).");

        return new()
        {
            ["final_result"] = FinalResultNotVerifiable, ["confirmed"] = confirmed, ["inferred"] = inferred, ["unverifiable"] = unverifiable,
        };
    }
}
