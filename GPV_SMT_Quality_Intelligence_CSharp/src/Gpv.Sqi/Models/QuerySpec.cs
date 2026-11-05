namespace Gpv.Sqi.Models;

/// <summary>
/// Filtro estructurado. Value: string, DateTimeOffset, int, bool o IReadOnlyList&lt;string&gt; (operador "in").
/// El frontend nunca envía texto OData.
/// </summary>
public sealed record Filter(string Field, string Op, object Value)
{
    public static readonly HashSet<string> AllowedOperators = ["eq", "ne", "ge", "gt", "le", "lt", "in"];

    public string Describe() => Op == "in" && Value is IReadOnlyList<string> list
        ? $"{Field} in [{list.Count} valores]"
        : $"{Field} {Op} {FormatValue(Value)}";

    private static string FormatValue(object v) => v switch
    {
        DateTimeOffset d => d.ToString("yyyy-MM-dd HH:mm:sszzz"),
        _ => v.ToString() ?? "",
    };
}

public sealed class QuerySpec
{
    public QuerySpec(string entity, IEnumerable<Filter>? filters = null, IEnumerable<(string Field, string Dir)>? orderBy = null,
                     int top = 50, IEnumerable<string>? select = null)
    {
        Entity = entity;
        Filters = filters?.ToList() ?? [];
        OrderBy = orderBy?.ToList() ?? [];
        Top = top;
        Select = select?.ToList();
    }

    public string Entity { get; }
    public List<Filter> Filters { get; }
    public List<(string Field, string Dir)> OrderBy { get; }
    public int Top { get; }
    public List<string>? Select { get; }

    public string Describe()
    {
        var parts = new List<string> { Entity };
        if (Filters.Count > 0) parts.Add("filtro: " + string.Join(" and ", Filters.Select(f => f.Describe())));
        if (OrderBy.Count > 0) parts.Add("orden: " + string.Join(", ", OrderBy.Select(o => $"{o.Field} {o.Dir}")));
        parts.Add($"top: {Top}");
        return string.Join(" | ", parts);
    }
}
