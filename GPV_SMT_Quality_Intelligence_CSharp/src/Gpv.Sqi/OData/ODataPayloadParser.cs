using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.OData;

public sealed class PayloadException(string message) : Exception(message);

public static class ODataPayloadParser
{
    /// <summary>
    /// Valida la estructura OData y devuelve (filas, nextLink). Acepta {"value":[...]} (v4),
    /// {"d":{"results":[...]}} (v2/v3) y {"d":[...]} (v1). Cualquier otra estructura es error.
    /// </summary>
    public static (List<JsonObject> Rows, string? NextLink) Parse(byte[] raw)
    {
        JsonNode? payload;
        try
        {
            var text = new UTF8Encoding(false, true).GetString(raw).TrimStart('﻿');
            payload = JsonNode.Parse(text);
        }
        catch (Exception ex) when (ex is JsonException or DecoderFallbackException or ArgumentException)
        {
            throw new PayloadException($"JSON inválido: {ex.GetType().Name}");
        }
        if (payload is not JsonObject obj) throw new PayloadException("La raíz JSON no es un objeto");

        JsonNode? rowsNode;
        string? next = null;
        if (obj.ContainsKey("value"))
        {
            rowsNode = obj["value"];
            next = Text(obj["@odata.nextLink"]) ?? Text(obj["odata.nextLink"]);
        }
        else if (obj.ContainsKey("d"))
        {
            var d = obj["d"];
            if (d is JsonArray) rowsNode = d;
            else if (d is JsonObject dobj && dobj["results"] is JsonArray results) { rowsNode = results; next = Text(dobj["__next"]); }
            else throw new PayloadException("Estructura 'd' inesperada");
        }
        else if (obj.ContainsKey("error") || obj.ContainsKey("odata.error"))
            throw new PayloadException("El servidor devolvió un objeto de error OData");
        else
            throw new PayloadException("No se encontró la colección 'value'");

        if (rowsNode is not JsonArray arr) throw new PayloadException("'value' no es una lista");
        var rows = new List<JsonObject>(arr.Count);
        foreach (var item in arr)
        {
            if (item is not JsonObject row) throw new PayloadException("Un registro no es un objeto JSON");
            var clean = new JsonObject();
            foreach (var (k, v) in row)
                if (!k.StartsWith("@odata") && !k.StartsWith("odata.") && k != "__metadata") clean[k] = v?.DeepClone();
            rows.Add(clean);
        }
        return (rows, next);
    }

    private static string? Text(JsonNode? n) => n is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;
}
