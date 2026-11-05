using System.Text.Json.Nodes;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;

namespace Gpv.Sqi.Data;

/// <summary>Auditoría de consultas, salud de conexión, historial de búsquedas y resultados de análisis.</summary>
public sealed class AuditRepository(Database db)
{
    private static string Now() => TimeParse.NowUtcIso();

    private void Write(Action<Microsoft.Data.Sqlite.SqliteConnection> action)
    {
        db.WriteLock.Wait();
        try { using var c = db.Open(); action(c); }
        finally { db.WriteLock.Release(); }
    }

    private List<Dictionary<string, object?>> Query(string sql, params object?[] ps)
    {
        using var c = db.Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = sql;
        Database.Bind(cmd, ps);
        return Database.ReadAll(cmd);
    }

    private static string Trunc(string? s, int n) => s is null ? "" : s.Length <= n ? s : s[..n];

    public void RecordQuery(QueryResult r) => Write(c =>
    {
        using (var cmd = c.CreateCommand())
        {
            cmd.CommandText = """
                INSERT INTO QueryAudit (ts, data_source, entity, query, status, http_status, elapsed_ms, wait_headers_ms,
                  download_ms, parse_ms, attempts, rows, error) VALUES ($p0,$p1,$p2,$p3,$p4,$p5,$p6,$p7,$p8,$p9,$p10,$p11,$p12)
                """;
            Database.Bind(cmd, Now(), r.DataSource, r.Entity, Trunc(r.QueryDescription, 500), r.Status.ToString(), r.HttpStatus,
                Math.Round(r.ElapsedMs, 1), r.Timings.TryGetValue("wait_headers_ms", out var w) ? w : null,
                r.Timings.TryGetValue("download_ms", out var d) ? d : null, r.Timings.TryGetValue("parse_ms", out var p) ? p : null,
                r.Attempts, r.Rows.Count, Trunc(r.Error, 500));
            cmd.ExecuteNonQuery();
        }
        if (r.Status is ODataStatus.VALIDATION_ERROR or ODataStatus.NOT_REQUESTED) return;
        var ok = r.Ok;
        using var up = c.CreateCommand();
        up.CommandText = """
            INSERT INTO ConnectionHealth (entity, data_source, last_status, last_http, last_elapsed_ms, last_checked_at,
              last_success_at, last_error_at, last_error, consecutive_failures)
            VALUES ($p0,$p1,$p2,$p3,$p4,$p5,$p6,$p7,$p8,$p9)
            ON CONFLICT(entity, data_source) DO UPDATE SET
              last_status=excluded.last_status, last_http=excluded.last_http, last_elapsed_ms=excluded.last_elapsed_ms,
              last_checked_at=excluded.last_checked_at,
              last_success_at=COALESCE(excluded.last_success_at, ConnectionHealth.last_success_at),
              last_error_at=COALESCE(excluded.last_error_at, ConnectionHealth.last_error_at),
              last_error=COALESCE(excluded.last_error, ConnectionHealth.last_error),
              consecutive_failures=CASE WHEN $p10 THEN 0 ELSE ConnectionHealth.consecutive_failures + 1 END
            """;
        Database.Bind(up, r.Entity, r.DataSource, r.Status.ToString(), r.HttpStatus, Math.Round(r.ElapsedMs, 1), Now(),
            ok ? Now() : null, ok ? null : Now(), ok ? null : Trunc(r.Error ?? r.Status.ToString(), 500), ok ? 0 : 1, ok ? 1 : 0);
        up.ExecuteNonQuery();
    });

    public List<Dictionary<string, object?>> Health(string ds) =>
        Query("SELECT * FROM ConnectionHealth WHERE data_source=$p0 ORDER BY entity", ds);

    public List<Dictionary<string, object?>> RecentQueries(int limit = 50) =>
        Query("SELECT * FROM QueryAudit ORDER BY id DESC LIMIT $p0", limit);

    public void AddSearch(string ds, string module, string term, string summary) => Write(c =>
    {
        using var cmd = c.CreateCommand();
        cmd.CommandText = "INSERT INTO SearchHistory (ts, data_source, module, term, summary) VALUES ($p0,$p1,$p2,$p3,$p4)";
        Database.Bind(cmd, Now(), ds, module, Trunc(term, 200), Trunc(summary, 300));
        cmd.ExecuteNonQuery();
    });

    public List<Dictionary<string, object?>> Searches(int limit = 100) =>
        Query("SELECT * FROM SearchHistory ORDER BY id DESC LIMIT $p0", limit);

    public void ClearSearches() => Write(c =>
    {
        using var cmd = c.CreateCommand();
        cmd.CommandText = "DELETE FROM SearchHistory";
        cmd.ExecuteNonQuery();
    });

    public void SaveAnalysis(string ds, string kind, string subject, object result) => Write(c =>
    {
        using var cmd = c.CreateCommand();
        cmd.CommandText = "INSERT INTO AnalysisResults (ts, data_source, kind, subject, result_json) VALUES ($p0,$p1,$p2,$p3,$p4)";
        Database.Bind(cmd, Now(), ds, kind, subject, Json.Serialize(result));
        cmd.ExecuteNonQuery();
    });

    public JsonObject? LatestAnalysis(string ds, string kind, string subject)
    {
        var rows = Query("SELECT result_json FROM AnalysisResults WHERE data_source=$p0 AND kind=$p1 AND subject=$p2 ORDER BY id DESC LIMIT 1",
                         ds, kind, subject);
        return rows.Count == 0 ? null : JsonNode.Parse((string)rows[0]["result_json"]!)!.AsObject();
    }
}
