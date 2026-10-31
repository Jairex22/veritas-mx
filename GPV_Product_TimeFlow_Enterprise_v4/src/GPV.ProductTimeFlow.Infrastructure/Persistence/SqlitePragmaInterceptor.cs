using System.Data.Common;
using Microsoft.EntityFrameworkCore.Diagnostics;

namespace GPV.ProductTimeFlow.Infrastructure.Persistence;

/// <summary>
/// Ajustes por conexión para SQLite (solo DEMO/desarrollo): WAL permite lecturas concurrentes con una escritura,
/// synchronous=NORMAL evita un fsync por transacción (seguro en WAL frente a corrupción) y foreign_keys garantiza integridad.
/// </summary>
public sealed class SqlitePragmaInterceptor : DbConnectionInterceptor
{
    private const string Pragmas = "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=30000;";

    public override void ConnectionOpened(DbConnection connection, ConnectionEndEventData eventData)
    {
        using var cmd = connection.CreateCommand();
        cmd.CommandText = Pragmas;
        cmd.ExecuteNonQuery();
    }

    public override async Task ConnectionOpenedAsync(DbConnection connection, ConnectionEndEventData eventData, CancellationToken cancellationToken = default)
    {
        await using var cmd = connection.CreateCommand();
        cmd.CommandText = Pragmas;
        await cmd.ExecuteNonQueryAsync(cancellationToken);
    }
}
