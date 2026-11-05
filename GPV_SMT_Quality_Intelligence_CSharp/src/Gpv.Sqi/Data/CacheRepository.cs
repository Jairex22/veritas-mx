using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;

namespace Gpv.Sqi.Data;

/// <summary>Caché local de registros OData con deduplicación segura. 'live' y 'demo' nunca se mezclan.</summary>
public sealed class CacheRepository(Database db)
{
    private static string? Utc(string? value)
    {
        var t = TimeParse.Parse(value);
        return t is { HasOffset: true } p ? TimeParse.Iso(p.Value.ToUniversalTime(), millis: true) : null;
    }

    /// <summary>Clave estable: ODataKey solo si es un GUID válido y no vacío; si no, hash del registro completo.</summary>
    public static string DedupKey(string entity, JsonObject row)
    {
        var key = row.Str("ODataKey");
        if (key is not null && ODataFilterBuilder.GuidRe().IsMatch(key) && !key.Equals(Entities.EmptyGuid, StringComparison.OrdinalIgnoreCase))
            return "key:" + key.ToLowerInvariant();
        var canonical = "{\"entity\":" + System.Text.Json.JsonSerializer.Serialize(entity) + ",\"row\":" + Json.Canonical(row) + "}";
        return "hash:" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)));
    }

    public int Store(string entity, IReadOnlyList<JsonObject> rows, string dataSource)
    {
        if ((dataSource != "live" && dataSource != "demo") || rows.Count == 0) return 0;
        var now = TimeParse.NowUtcIso();
        db.WriteLock.Wait();
        try
        {
            using var c = db.Open();
            using var tx = c.BeginTransaction();
            foreach (var r in rows)
            {
                using var cmd = c.CreateCommand();
                cmd.Transaction = tx;
                var raw = r.ToJsonString(Json.Options);
                var k = DedupKey(entity, r);
                switch (entity)
                {
                    case "SMT":
                        cmd.CommandText = """
                            INSERT INTO CachedSMTEvents (dedup_key, data_source, identifier, batch, assembly, customer, operation,
                              event_date, event_utc, odata_key, raw_json, first_seen_at, last_seen_at)
                            VALUES ($p0,$p1,$p2,$p3,$p4,$p5,$p6,$p7,$p8,$p9,$p10,$p11,$p12)
                            ON CONFLICT(data_source, dedup_key) DO UPDATE SET last_seen_at=excluded.last_seen_at
                            """;
                        Database.Bind(cmd, k, dataSource, r.Str("Identifier"), r.Str("Batch"), r.Str("Assembly"), r.Str("Customer"),
                            r.Str("OperationName"), r.Str("EventDate"), Utc(r.Str("EventDate")), r.Str("ODataKey"), raw, now, now);
                        break;
                    case "Quality":
                        cmd.CommandText = """
                            INSERT INTO CachedQualityDefects (dedup_key, data_source, defect_id, identifier, batch, assembly,
                              defect_status, line, date_created, created_utc, odata_key, raw_json, first_seen_at, last_seen_at)
                            VALUES ($p0,$p1,$p2,$p3,$p4,$p5,$p6,$p7,$p8,$p9,$p10,$p11,$p12,$p13)
                            ON CONFLICT(data_source, dedup_key) DO UPDATE SET last_seen_at=excluded.last_seen_at
                            """;
                        Database.Bind(cmd, k, dataSource, r.Str("DefectID"), r.Str("Identifier"), r.Str("BatchName"), r.Str("Assembly"),
                            r.Str("DefectStatus"), r.Str("Line"), r.Str("DateCreated"), Utc(r.Str("DateCreated")), r.Str("ODataKey"), raw, now, now);
                        break;
                    case "QualityHistory":
                        cmd.CommandText = """
                            INSERT INTO CachedQualityHistory (dedup_key, data_source, defect_id, identifier, history_time, history_utc,
                              history_status, operation, odata_key, raw_json, first_seen_at, last_seen_at)
                            VALUES ($p0,$p1,$p2,$p3,$p4,$p5,$p6,$p7,$p8,$p9,$p10,$p11)
                            ON CONFLICT(data_source, dedup_key) DO UPDATE SET last_seen_at=excluded.last_seen_at
                            """;
                        Database.Bind(cmd, k, dataSource, r.Str("DefectID"), r.Str("Identifier"), r.Str("DefectHistoryTime"),
                            Utc(r.Str("DefectHistoryTime")), r.Str("DefectHistoryStatus"), r.Str("DefectHistoryOperation"), r.Str("ODataKey"), raw, now, now);
                        break;
                    default:
                        throw new ArgumentException($"Entidad no cacheable: {entity}");
                }
                cmd.ExecuteNonQuery();
            }
            tx.Commit();
        }
        finally { db.WriteLock.Release(); }
        return rows.Count;
    }

    private (List<JsonObject> Rows, string? CachedAt) Fetch(string sql, params object?[] ps)
    {
        using var c = db.Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = sql;
        Database.Bind(cmd, ps);
        var rows = Database.ReadAll(cmd);
        if (rows.Count == 0) return ([], null);
        return (rows.Select(r => JsonNode.Parse((string)r["raw_json"]!)!.AsObject()).ToList(),
                rows.Select(r => (string)r["last_seen_at"]!).Max(StringComparer.Ordinal));
    }

    private static string U(DateTimeOffset d) => TimeParse.Iso(d.ToUniversalTime(), millis: true);

    public (List<JsonObject> Rows, string? CachedAt) SmtByIdentifier(string identifier, string ds) =>
        Fetch("SELECT raw_json, last_seen_at FROM CachedSMTEvents WHERE data_source=$p0 AND identifier=$p1 ORDER BY event_utc", ds, identifier);

    public (List<JsonObject> Rows, string? CachedAt) SmtInWindow(DateTimeOffset start, DateTimeOffset end, string ds, int limit) =>
        Fetch("SELECT raw_json, last_seen_at FROM CachedSMTEvents WHERE data_source=$p0 AND event_utc>=$p1 AND event_utc<=$p2 ORDER BY event_utc DESC LIMIT $p3",
              ds, U(start), U(end), limit);

    public (List<JsonObject> Rows, string? CachedAt) QualityByIdentifier(string identifier, string ds) =>
        Fetch("SELECT raw_json, last_seen_at FROM CachedQualityDefects WHERE data_source=$p0 AND identifier=$p1", ds, identifier);

    public (List<JsonObject> Rows, string? CachedAt) QualityInWindow(DateTimeOffset start, DateTimeOffset end, string ds, int limit) =>
        Fetch("SELECT raw_json, last_seen_at FROM CachedQualityDefects WHERE data_source=$p0 AND created_utc>=$p1 AND created_utc<=$p2 ORDER BY created_utc DESC LIMIT $p3",
              ds, U(start), U(end), limit);

    public (List<JsonObject> Rows, string? CachedAt) QualityByDefect(string defectId, string ds) =>
        Fetch("SELECT raw_json, last_seen_at FROM CachedQualityDefects WHERE data_source=$p0 AND lower(defect_id)=$p1 ORDER BY id DESC", ds, defectId.ToLowerInvariant());

    public (List<JsonObject> Rows, string? CachedAt) HistoryByDefects(IReadOnlyList<string> defectIds, string ds)
    {
        if (defectIds.Count == 0) return ([], null);
        var marks = string.Join(",", defectIds.Select((_, i) => $"$p{i + 1}"));
        return Fetch($"SELECT raw_json, last_seen_at FROM CachedQualityHistory WHERE data_source=$p0 AND lower(defect_id) IN ({marks}) ORDER BY history_utc",
                     [ds, .. defectIds.Select(d => (object?)d.ToLowerInvariant())]);
    }

    public Dictionary<string, object?> Counts()
    {
        using var c = db.Open();
        var outD = new Dictionary<string, object?>();
        foreach (var t in new[] { "CachedSMTEvents", "CachedQualityDefects", "CachedQualityHistory" })
        {
            using var cmd = c.CreateCommand();
            cmd.CommandText = $"SELECT COUNT(*) FROM {t}";
            outD[t] = Convert.ToInt64(cmd.ExecuteScalar());
        }
        return outD;
    }
}
