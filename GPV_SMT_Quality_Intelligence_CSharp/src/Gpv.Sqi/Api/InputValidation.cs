using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Gpv.Sqi.OData;

namespace Gpv.Sqi.Api;

public sealed class InputException(string message) : Exception(message);

/// <summary>Validación de entradas del usuario.</summary>
public static partial class InputValidation
{
    public const int IdentifierMax = 64;
    public const int TermMax = 100;

    // Alfanuméricos y separadores habituales; se rechazan comillas, barras invertidas, control y espacios.
    [GeneratedRegex(@"^[A-Za-z0-9][A-Za-z0-9._\-/#+:$()]*$")]
    private static partial Regex IdentRe();

    [GeneratedRegex("^[^\\x00-\\x1f\\x7f'\"\\\\<>]+$")]
    private static partial Regex TermRe();

    public static string NewToken() => Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    public static string? GetString(JsonObject body, string key) =>
        body.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;

    public static string Identifier(JsonObject body, string key = "identifier")
    {
        if (body.TryGetPropertyValue(key, out var n) && n is not null && !(n is JsonValue jv && jv.TryGetValue<string>(out _)))
            throw new InputException("El número de serie debe ser texto");
        return Identifier(GetString(body, key));
    }

    public static string Identifier(string? value)
    {
        if (value is null) throw new InputException("El número de serie debe ser texto");
        var v = value.Trim();
        if (v.Length == 0) throw new InputException("Escanea o escribe un número de serie");
        if (v.Length > IdentifierMax) throw new InputException($"El número de serie excede {IdentifierMax} caracteres");
        if (!IdentRe().IsMatch(v)) throw new InputException("El número de serie contiene caracteres no permitidos");
        return v;
    }

    public static string? Term(JsonObject body, string key, string name, bool required = false)
    {
        if (!body.TryGetPropertyValue(key, out var n) || n is null) return Term((string?)null, name, required);
        if (n is not JsonValue v || !v.TryGetValue<string>(out var s)) throw new InputException($"{name} debe ser texto");
        return Term(s, name, required);
    }

    public static string? Term(string? value, string name, bool required = false)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            if (required) throw new InputException($"{name} es obligatorio");
            return null;
        }
        var v = value.Trim();
        if (v.Length > TermMax) throw new InputException($"{name} excede {TermMax} caracteres");
        if (!TermRe().IsMatch(v)) throw new InputException($"{name} contiene caracteres no permitidos");
        return v;
    }

    public static string Guid(JsonNode? value)
    {
        if (value is not JsonValue v || !v.TryGetValue<string>(out var s) || !ODataFilterBuilder.GuidRe().IsMatch(s.Trim()))
            throw new InputException("DefectID inválido");
        return s.Trim();
    }

    public static DateTimeOffset ClientDateTime(string? value, string name)
    {
        if (value is null || value.Length > 40) throw new InputException($"{name}: fecha inválida");
        var hasOffset = Regex.IsMatch(value, @"(Z|[+-]\d{2}:?\d{2})$");
        if (!hasOffset) throw new InputException($"{name}: la fecha debe incluir zona horaria");
        if (!DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.None, out var d))
            throw new InputException($"{name}: fecha inválida");
        return d;
    }

    public static JsonObject ParseBody(string raw)
    {
        try
        {
            var node = JsonNode.Parse(string.IsNullOrWhiteSpace(raw) ? "{}" : raw);
            return node as JsonObject ?? throw new InputException("Se esperaba un objeto JSON");
        }
        catch (JsonException) { throw new InputException("JSON inválido"); }
    }
}
