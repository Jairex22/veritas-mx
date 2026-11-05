using System.Globalization;
using System.Text.RegularExpressions;
using Gpv.Sqi.Models;

namespace Gpv.Sqi.OData;

public sealed class FilterException(string message) : Exception(message);

/// <summary>
/// Construcción segura de URLs OData: solo entidades/campos de la lista blanca, literales
/// según el tipo Edm real y la versión OData, comillas duplicadas y valores codificados en URL.
/// </summary>
public static partial class ODataFilterBuilder
{
    public const int MaxStringLiteral = 200;
    public const int MaxInValues = 10;
    public const int MaxTop = 1000;

    [GeneratedRegex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")]
    public static partial Regex GuidRe();

    public static string EscapeStringLiteral(string value)
    {
        if (value.Length > MaxStringLiteral) throw new FilterException("Valor demasiado largo");
        if (value.Any(c => c < 32 || c == 127)) throw new FilterException("El valor contiene caracteres de control");
        return "'" + value.Replace("'", "''") + "'";
    }

    private static DateTimeOffset ToUtc(object value) => value is DateTimeOffset d
        ? d.ToUniversalTime()
        : throw new FilterException(value is DateTime ? "La fecha debe incluir zona horaria" : "Se esperaba fecha/hora");

    public static string FormatLiteral(object value, string edmType, string odataVersion)
    {
        var v4 = odataVersion == "4";
        switch (edmType)
        {
            case "Edm.String":
                return EscapeStringLiteral(value as string ?? Convert.ToString(value, CultureInfo.InvariantCulture) ?? "");
            case "Edm.Guid":
            {
                var s = value as string ?? "";
                if (!GuidRe().IsMatch(s)) throw new FilterException("GUID inválido");
                return v4 ? s : $"guid'{s}'";
            }
            case "Edm.DateTimeOffset":
            {
                var s = ToUtc(value).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
                return v4 ? s : $"datetimeoffset'{s}'";
            }
            case "Edm.DateTime":
            {
                var s = ToUtc(value).ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture);
                return v4 ? s : $"datetime'{s}'";
            }
            case "Edm.Int32" or "Edm.Int64" or "Edm.Int16":
                return value is int or long or short ? Convert.ToString(value, CultureInfo.InvariantCulture)! : throw new FilterException("Se esperaba número entero");
            case "Edm.Boolean":
                return value is bool b ? (b ? "true" : "false") : throw new FilterException("Se esperaba booleano");
            default:
                throw new FilterException($"Tipo {edmType} no soportado para filtros");
        }
    }

    public static string BuildFilter(QuerySpec spec, IReadOnlyDictionary<string, PropertyInfo> props, string odataVersion)
    {
        var allowed = Entities.Filterable.GetValueOrDefault(spec.Entity) ?? [];
        var clauses = new List<string>();
        foreach (var f in spec.Filters)
        {
            if (!allowed.Contains(f.Field)) throw new FilterException($"Campo no autorizado para filtrar: {f.Field}");
            if (!props.TryGetValue(f.Field, out var prop)) throw new FilterException($"El campo {f.Field} no existe en $metadata de {spec.Entity}");
            if (!Filter.AllowedOperators.Contains(f.Op)) throw new FilterException($"Operador no autorizado: {f.Op}");
            if (f.Op == "in")
            {
                if (f.Value is not IReadOnlyList<string> values || values.Count == 0 || values.Count > MaxInValues)
                    throw new FilterException("Lista de valores vacía o demasiado grande");
                clauses.Add("(" + string.Join(" or ", values.Select(v => $"{f.Field} eq {FormatLiteral(v, prop.EdmType, odataVersion)}")) + ")");
            }
            else
            {
                clauses.Add($"{f.Field} {f.Op} {FormatLiteral(f.Value, prop.EdmType, odataVersion)}");
            }
        }
        return string.Join(" and ", clauses);
    }

    public static string BuildQueryUrl(string baseUrl, QuerySpec spec, IReadOnlyDictionary<string, PropertyInfo>? props, string odataVersion)
    {
        if (!Entities.Known.TryGetValue(spec.Entity, out var known)) throw new FilterException($"Entidad no autorizada: {spec.Entity}");
        props ??= known;
        if (spec.Top < 1 || spec.Top > MaxTop) throw new FilterException("$top fuera de rango");
        var ps = new List<(string, string)>();
        var flt = BuildFilter(spec, props, odataVersion);
        if (flt.Length > 0) ps.Add(("$filter", flt));
        if (spec.OrderBy.Count > 0)
        {
            foreach (var (fld, dir) in spec.OrderBy)
                if (!props.ContainsKey(fld) || (dir != "asc" && dir != "desc")) throw new FilterException("Orden no autorizado");
            ps.Add(("$orderby", string.Join(",", spec.OrderBy.Select(o => $"{o.Field} {o.Dir}"))));
        }
        if (spec.Select is { Count: > 0 })
        {
            var sel = spec.Select.Where(props.ContainsKey).ToList();
            if (sel.Count > 0) ps.Add(("$select", string.Join(",", sel)));
        }
        ps.Add(("$top", spec.Top.ToString(CultureInfo.InvariantCulture)));
        var query = string.Join("&", ps.Select(p => $"{p.Item1}={Uri.EscapeDataString(p.Item2).Replace("'", "%27")}"));
        return baseUrl.TrimEnd('/') + "/" + Uri.EscapeDataString(spec.Entity) + "?" + query;
    }
}
