using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace GPV.ProductTimeFlow.Infrastructure.Persistence;

/// <summary>Fábricas para "dotnet ef" (migraciones). No se usan en tiempo de ejecución.</summary>
public sealed class SqliteDesignTimeFactory : IDesignTimeDbContextFactory<SqliteTimeFlowDbContext>
{
    public SqliteTimeFlowDbContext CreateDbContext(string[] args) =>
        new(new DbContextOptionsBuilder<SqliteTimeFlowDbContext>().UseSqlite("Data Source=design-time.db").Options);
}

public sealed class SqlServerDesignTimeFactory : IDesignTimeDbContextFactory<SqlServerTimeFlowDbContext>
{
    public SqlServerTimeFlowDbContext CreateDbContext(string[] args) =>
        new(new DbContextOptionsBuilder<SqlServerTimeFlowDbContext>()
            .UseSqlServer("Server=localhost;Database=GpvProductTimeFlow;Integrated Security=true;TrustServerCertificate=true").Options);
}
