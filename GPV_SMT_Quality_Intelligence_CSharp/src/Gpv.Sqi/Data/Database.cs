using System.Reflection;
using Microsoft.Data.Sqlite;

namespace Gpv.Sqi.Data;

/// <summary>SQLite: una conexión por operación; escrituras serializadas.</summary>
public sealed class Database
{
    public const int SchemaVersion = 1;
    private readonly string _connectionString;
    public SemaphoreSlim WriteLock { get; } = new(1, 1);
    public string Path { get; }

    public Database(string path)
    {
        Path = path;
        var dir = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        _connectionString = new SqliteConnectionStringBuilder { DataSource = path, DefaultTimeout = 10, Pooling = false }.ToString();
        Initialize();
    }

    public SqliteConnection Open()
    {
        var c = new SqliteConnection(_connectionString);
        c.Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = "PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;";
        cmd.ExecuteNonQuery();
        return c;
    }

    private void Initialize()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("schema.sql")
                           ?? throw new InvalidOperationException("schema.sql no está incrustado");
        using var reader = new StreamReader(stream);
        var schema = reader.ReadToEnd();
        using var c = Open();
        using (var cmd = c.CreateCommand()) { cmd.CommandText = schema; cmd.ExecuteNonQuery(); }
        using var check = c.CreateCommand();
        check.CommandText = "SELECT COUNT(*) FROM SchemaVersion";
        if (Convert.ToInt64(check.ExecuteScalar()) == 0)
        {
            using var ins = c.CreateCommand();
            ins.CommandText = "INSERT INTO SchemaVersion (version) VALUES ($v)";
            ins.Parameters.AddWithValue("$v", SchemaVersion);
            ins.ExecuteNonQuery();
        }
    }

    public static void Bind(SqliteCommand cmd, params object?[] values)
    {
        for (var i = 0; i < values.Length; i++) cmd.Parameters.AddWithValue($"$p{i}", values[i] ?? DBNull.Value);
    }

    public static List<Dictionary<string, object?>> ReadAll(SqliteCommand cmd)
    {
        using var r = cmd.ExecuteReader();
        var rows = new List<Dictionary<string, object?>>();
        while (r.Read())
        {
            var row = new Dictionary<string, object?>();
            for (var i = 0; i < r.FieldCount; i++) row[r.GetName(i)] = r.IsDBNull(i) ? null : r.GetValue(i);
            rows.Add(row);
        }
        return rows;
    }
}
