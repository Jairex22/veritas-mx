using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.Analytics;

/// <summary>
/// Motor de reglas de reproceso y bucles (auditable). Cada alerta incluye regla, categoría, confianza,
/// evidencia y lo que NO puede concluirse. Un bucle solo se confirma con un flujo autorizado configurado.
/// </summary>
public static class ReworkRules
{
    public static readonly (string Id, string Category, string Title, string Definition)[] Rules =
    [
        ("R01", "DUPLICATE_EVENT", "Evento duplicado", "Dos o más eventos con el mismo Identifier, OperationName y EventDate exacto."),
        ("R02", "REPEATED_OPERATION", "Operación repetida", "La misma OperationName aparece en momentos distintos para el mismo Identifier."),
        ("R03", "REPAIR_RECORDED", "Reparación registrada", "Se observó una operación cuyo nombre coincide con una palabra clave de reparación configurada."),
        ("R04", "POSSIBLE_REWORK", "Posible reproceso", "Operación repetida acompañada de una reparación registrada o de un defecto asociado."),
        ("R05", "POST_REPAIR_EVENTS", "Eventos posteriores a reparación", "Existen operaciones registradas después de la última reparación."),
        ("R06", "DEFECT_CLOSED", "Defecto cerrado", "El defecto tiene estado Closed. No constituye evidencia de aprobación final."),
        ("R07", "CONFIRMED_LOOP", "Bucle de proceso confirmado", "La secuencia regresa a un paso anterior del flujo autorizado configurado para el ensamble."),
        ("R08", "LOOP_NOT_CONFIRMABLE", "Bucle no confirmable", "Hay repetición de operaciones pero no existe un flujo autorizado configurado para confirmarlo."),
        ("R09", "TIME_ORDER_REVIEW", "Orden temporal a revisar", "Un defecto se registró antes del primer evento de su operación de origen; verificar zonas horarias."),
    ];

    public static List<Dictionary<string, object?>> PublicRules() =>
        Rules.Select(r => new Dictionary<string, object?> { ["rule"] = r.Id, ["category"] = r.Category, ["title"] = r.Title, ["definition"] = r.Definition }).ToList();

    private static Dictionary<string, object?> Alert(string rule, string confidence, List<string> evidence, string explanation, List<string> cannot)
    {
        var r = Rules.First(x => x.Id == rule);
        return new()
        {
            ["rule"] = rule, ["category"] = r.Category, ["title"] = r.Title, ["definition"] = r.Definition, ["confidence"] = confidence,
            ["evidence"] = evidence, ["explanation"] = explanation, ["cannot_conclude"] = cannot,
        };
    }

    public static bool IsRepair(string? op, IReadOnlyList<string> keywords)
    {
        var up = (op ?? "").ToUpperInvariant();
        return keywords.Any(k => !string.IsNullOrEmpty(k) && up.Contains(k.ToUpperInvariant()));
    }

    public static List<Dictionary<string, object?>> Evaluate(string identifier, IReadOnlyList<JsonObject> smt,
        IReadOnlyList<Dictionary<string, object?>> defects, IReadOnlyList<string> repairKeywords, IReadOnlyDictionary<string, List<string>> processFlows)
    {
        var events = smt.Select((r, i) => (Idx: i + 1, Row: r)).OrderBy(p => TimeParse.SortKey(p.Row.Str("EventDate"))).ToList();
        var alerts = new List<Dictionary<string, object?>>();

        // R01 / R02
        var byOp = new Dictionary<string, List<(int Idx, JsonObject Row)>>();
        foreach (var e in events)
        {
            var op = Json.IsBlank(e.Row.Str("OperationName")) ? "(sin nombre)" : e.Row.Str("OperationName")!;
            if (!byOp.TryGetValue(op, out var l)) byOp[op] = l = [];
            l.Add(e);
        }
        var repeatedOps = new List<string>();
        foreach (var (op, lst) in byOp)
        {
            var stamps = new Dictionary<string, List<int>>();
            foreach (var (idx, r) in lst)
            {
                var ts = Json.PyStr(r.Str("EventDate"));
                if (!stamps.TryGetValue(ts, out var l)) stamps[ts] = l = [];
                l.Add(idx);
            }
            foreach (var (ts, idxs) in stamps)
                if (idxs.Count > 1)
                    alerts.Add(Alert("R01", "alta", idxs.Select(i => $"SMT#{i}").ToList(),
                        $"'{op}' registrada {idxs.Count} veces con EventDate {ts}.",
                        ["Si corresponde a dos pasos físicos o a un registro duplicado en el MES."]));
            if (stamps.Count > 1)
            {
                repeatedOps.Add(op);
                alerts.Add(Alert("R02", "alta", lst.Select(p => $"SMT#{p.Idx}").ToList(),
                    $"'{op}' aparece {stamps.Count} veces en momentos distintos.",
                    ["Que se trate de tarjetas distintas (es el mismo Identifier).", "Que la repetición sea un bucle de proceso real.", "La causa de la repetición."]));
            }
        }

        // R03 / R05
        var repairs = events.Where(e => IsRepair(e.Row.Str("OperationName"), repairKeywords)).ToList();
        if (repairs.Count > 0)
        {
            alerts.Add(Alert("R03", "alta", repairs.Select(p => $"SMT#{p.Idx}").ToList(),
                $"{repairs.Count} evento(s) de reparación: " + string.Join(", ", repairs.Select(p => p.Row.Str("OperationName") ?? "").Distinct().Order(StringComparer.Ordinal)),
                ["La acción física exacta realizada por el técnico.", "Que la reparación haya sido exitosa."]));
            var lastRepair = TimeParse.Parse(repairs[^1].Row.Str("EventDate"));
            if (lastRepair is not null)
            {
                var after = events.Where(e => (TimeParse.Parse(e.Row.Str("EventDate")) ?? lastRepair).Value.Value > lastRepair.Value.Value).ToList();
                if (after.Count > 0)
                    alerts.Add(Alert("R05", "alta", after.Select(p => $"SMT#{p.Idx}").ToList(),
                        "Operaciones después de la última reparación: " + string.Join(", ", after.Select(p => Json.IsBlank(p.Row.Str("OperationName")) ? "?" : p.Row.Str("OperationName"))),
                        ["Que estas operaciones hayan resultado en aprobación (PASS)."]));
            }
        }

        // R04
        if (repeatedOps.Count > 0 && (repairs.Count > 0 || defects.Count > 0))
        {
            var reasons = new List<string>();
            if (repairs.Count > 0) reasons.Add("reparación registrada");
            if (defects.Count > 0) reasons.Add($"{defects.Count} defecto(s) único(s) asociado(s)");
            var ev = repeatedOps.SelectMany(op => byOp[op].Select(p => $"SMT#{p.Idx}"))
                .Concat(defects.Select(d => $"DEF:{Json.PyStr((string?)d["defect_id"])}")).ToList();
            alerts.Add(Alert("R04", "media", ev,
                $"Operación(es) repetida(s) {string.Join(", ", repeatedOps)} con " + string.Join(" y ", reasons) + ".",
                ["Que el reproceso esté confirmado: requiere el registro de la acción física.", "Que la unidad haya sido aprobada al final."]));
        }

        // R06
        foreach (var d in defects)
        {
            if (!string.Equals((string?)d["status"], "closed", StringComparison.OrdinalIgnoreCase)) continue;
            var ev = new List<string> { $"DEF:{Json.PyStr((string?)d["defect_id"])}" };
            if (!Json.IsBlank((string?)d["closed_at"])) ev.Add($"Cierre {d["closed_at"]}");
            var desc = Json.IsBlank((string?)d["description"]) ? Json.PyStr((string?)d["defect_id"]) : (string)d["description"]!;
            var closedOp = (string?)d["closed_operation"];
            alerts.Add(Alert("R06", "alta", ev,
                $"Defecto {desc} con estado Closed" + (Json.IsBlank(closedOp) ? "" : $" (cierre registrado en {closedOp})") + ".",
                ["Que la PCBA esté aprobada o sea buena.", "La acción física realizada."]));
        }

        // R07 / R08
        var assembly = events.Select(e => e.Row.Str("Assembly")).FirstOrDefault(a => !Json.IsBlank(a));
        var flow = processFlows.GetValueOrDefault(assembly ?? "", []);
        if (flow.Count > 0)
        {
            var pos = new Dictionary<string, int>();
            for (var i = 0; i < flow.Count; i++) pos[flow[i]] = i;
            var maxPos = -1;
            var back = new List<int>();
            foreach (var (idx, r) in events)
            {
                if (!pos.TryGetValue(r.Str("OperationName") ?? "\0", out var p)) continue;
                if (p < maxPos) back.Add(idx);
                maxPos = Math.Max(maxPos, p);
            }
            if (back.Count > 0)
                alerts.Add(Alert("R07", "alta", back.Select(i => $"SMT#{i}").ToList(),
                    $"La secuencia regresa a un paso anterior del flujo autorizado de {assembly}.", ["La causa raíz del bucle."]));
        }
        else if (repeatedOps.Count > 0)
        {
            alerts.Add(Alert("R08", "n/a", [],
                $"No hay flujo autorizado configurado para el ensamble {(Json.IsBlank(assembly) ? "(desconocido)" : assembly)}; " +
                "un bucle real no puede confirmarse solo por repetición de operaciones.",
                ["Que exista un bucle de proceso real."]));
        }

        // R09
        foreach (var d in defects)
        {
            var created = TimeParse.Parse((string?)d["date_created"]);
            var src = (string?)d["source_operation"];
            var srcTimes = events.Where(e => e.Row.Str("OperationName") == src).Select(e => TimeParse.Parse(e.Row.Str("EventDate")))
                .Where(t => t is { HasOffset: true }).Select(t => t!.Value.Value).ToList();
            if (created is { HasOffset: true } c && srcTimes.Count > 0 && c.Value < srcTimes.Min())
            {
                var first = srcTimes.MinBy(t => t.UtcTicks);
                alerts.Add(Alert("R09", "baja", [$"DEF:{Json.PyStr((string?)d["defect_id"])}"],
                    $"DateCreated {d["date_created"]} es anterior al primer evento '{src}' ({TimeParse.Iso(first)}).",
                    ["Si la diferencia se debe a zona horaria, reloj del equipo o a un evento previo no registrado en SMT."]));
            }
        }
        return alerts;
    }
}
