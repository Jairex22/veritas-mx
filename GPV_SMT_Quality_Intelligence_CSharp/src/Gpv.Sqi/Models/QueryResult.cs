using System.Text.Json.Nodes;

namespace Gpv.Sqi.Models;

public sealed class QueryResult
{
    public QueryResult(ODataStatus status, string entity) { Status = status; Entity = entity; }

    public ODataStatus Status { get; set; }
    public string Entity { get; set; }
    public List<JsonObject> Rows { get; set; } = [];
    public int? HttpStatus { get; set; }
    public double ElapsedMs { get; set; }
    public Dictionary<string, double> Timings { get; set; } = new();
    public int Attempts { get; set; }
    public string? Error { get; set; }
    public string QueryDescription { get; set; } = "";
    public string DataSource { get; set; } = "live";   // live | demo
    public bool Truncated { get; set; }
    public bool Stale { get; set; }
    public string? CachedAt { get; set; }
    public string? FetchedAt { get; set; }

    public bool Ok => Status.IsSuccess();

    /// <summary>Resumen sin filas, apto para la UI y el diagnóstico.</summary>
    public Dictionary<string, object?> ToStatusDict() => new()
    {
        ["entity"] = Entity,
        ["status"] = Status.ToString(),
        ["label"] = Status.LabelEs(),
        ["ok"] = Ok,
        ["http_status"] = HttpStatus,
        ["elapsed_ms"] = Math.Round(ElapsedMs, 1),
        ["timings"] = Timings.ToDictionary(kv => kv.Key, kv => Math.Round(kv.Value, 1)),
        ["attempts"] = Attempts,
        ["error"] = Error,
        ["rows"] = Rows.Count,
        ["query"] = QueryDescription,
        ["data_source"] = DataSource,
        ["truncated"] = Truncated,
        ["stale"] = Stale,
        ["cached_at"] = CachedAt,
        ["fetched_at"] = FetchedAt,
    };
}
