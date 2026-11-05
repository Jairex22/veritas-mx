using System.Globalization;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Gpv.Sqi.Infrastructure;

public static class Json
{
    public static readonly JsonSerializerOptions Options = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,   // el frontend inserta texto con textContent
        WriteIndented = false,
    };

    public static string Serialize(object? value) => JsonSerializer.Serialize(value, Options);

    /// <summary>Lectura tolerante de un campo de un registro OData como texto.</summary>
    public static string? Str(this JsonObject row, string key)
    {
        if (!row.TryGetPropertyValue(key, out var node) || node is null) return null;
        if (node is JsonValue v)
        {
            if (v.TryGetValue<string>(out var s)) return s;
            if (v.TryGetValue<bool>(out var b)) return b ? "True" : "False";
            if (v.TryGetValue<JsonElement>(out var el)) return el.ValueKind == JsonValueKind.Null ? null : el.ToString();
            return v.ToJsonString().Trim('"');
        }
        return node.ToJsonString();
    }

    /// <summary>Equivalente a str(x) de Python para valores que pueden ser nulos.</summary>
    public static string PyStr(string? v) => v ?? "None";

    public static bool IsBlank(string? s) => string.IsNullOrEmpty(s);

    public static JsonObject Clone(this JsonObject row) => row.DeepClone().AsObject();

    public static List<JsonObject> ParseRows(string json)
    {
        var root = JsonNode.Parse(json)!.AsObject();
        return root["value"]!.AsArray().Select(n => n!.AsObject().Clone()).ToList();
    }

    /// <summary>JSON canónico (claves ordenadas) para claves de deduplicación.</summary>
    public static string Canonical(JsonNode? node) => node switch
    {
        null => "null",
        JsonObject o => "{" + string.Join(",", o.OrderBy(kv => kv.Key, StringComparer.Ordinal)
            .Select(kv => JsonSerializer.Serialize(kv.Key) + ":" + Canonical(kv.Value))) + "}",
        JsonArray a => "[" + string.Join(",", a.Select(Canonical)) + "]",
        _ => node.ToJsonString(),
    };

    public static string Num(double v) => v.ToString("0.##", CultureInfo.InvariantCulture);
}
