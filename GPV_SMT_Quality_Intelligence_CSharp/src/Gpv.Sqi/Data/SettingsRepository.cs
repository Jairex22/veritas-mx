using System.Text.Json.Nodes;
using Gpv.Sqi.Config;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.Data;

/// <summary>Ajustes editables desde la interfaz (sin secretos).</summary>
public sealed class SettingsRepository(Database db)
{
    public Dictionary<string, JsonNode?> All()
    {
        using var c = db.Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = "SELECT key, value_json FROM ApplicationSettings";
        return Database.ReadAll(cmd).Where(r => AppConfig.EditableKeys.ContainsKey((string)r["key"]!))
            .ToDictionary(r => (string)r["key"]!, r => JsonNode.Parse((string)r["value_json"]!));
    }

    public void Save(IReadOnlyDictionary<string, JsonNode> values)
    {
        var now = TimeParse.NowUtcIso();
        db.WriteLock.Wait();
        try
        {
            using var c = db.Open();
            using var tx = c.BeginTransaction();
            foreach (var (k, v) in values)
            {
                if (!AppConfig.EditableKeys.ContainsKey(k)) throw new ArgumentException($"Clave no editable: {k}");
                using var cmd = c.CreateCommand();
                cmd.Transaction = tx;
                cmd.CommandText = "INSERT INTO ApplicationSettings (key, value_json, updated_at) VALUES ($p0,$p1,$p2) " +
                                  "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at";
                Database.Bind(cmd, k, v.ToJsonString(), now);
                cmd.ExecuteNonQuery();
            }
            tx.Commit();
        }
        finally { db.WriteLock.Release(); }
    }

    public void Reset()
    {
        db.WriteLock.Wait();
        try
        {
            using var c = db.Open();
            using var cmd = c.CreateCommand();
            cmd.CommandText = "DELETE FROM ApplicationSettings";
            cmd.ExecuteNonQuery();
        }
        finally { db.WriteLock.Release(); }
    }
}
