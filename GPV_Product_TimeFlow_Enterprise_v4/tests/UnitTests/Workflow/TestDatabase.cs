using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure;
using GPV.ProductTimeFlow.Shared;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace GPV.ProductTimeFlow.UnitTests.Workflow;

internal sealed class TestHostEnvironment(string root) : IHostEnvironment
{
    public string EnvironmentName { get; set; } = "Testing";
    public string ApplicationName { get; set; } = "GPV.ProductTimeFlow.UnitTests";
    public string ContentRootPath { get; set; } = root;
    public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
}

internal sealed class NullRealtimeNotifier : IRealtimeNotifier
{
    public Task PushAsync(IReadOnlyCollection<(int EmployeeId, NotificationDto Notification)> items, CancellationToken ct) => Task.CompletedTask;
}

/// <summary>
/// Base de datos SQLite real (archivo temporal) construida con la misma DI de Infrastructure. Una instancia por prueba.
/// </summary>
internal sealed class TestDatabase : IAsyncDisposable
{
    public const string Password = "Demo#TimeFlow2026";
    public const string Domain = "demo.timeflow.example";

    public string Root { get; }
    public ServiceProvider Services { get; }

    private TestDatabase(string root, ServiceProvider services) { Root = root; Services = services; }

    public static async Task<TestDatabase> CreateAsync()
    {
        var root = Path.Combine(Path.GetTempPath(), $"tf-tests-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["TimeFlow:Mode"] = "Demo",
            ["TimeFlow:DataRoot"] = root,
            ["TimeFlow:PublicBaseUrl"] = "https://localhost",
            ["Database:Provider"] = "Sqlite",
            ["Demo:SyntheticEmployees"] = "12",
            ["Demo:SeedSampleRequests"] = "false",
            ["Email:Provider"] = "Mock",
            ["Email:ProcessorEnabled"] = "false",
        }).Build();

        var services = new ServiceCollection();
        services.AddLogging(b => b.SetMinimumLevel(LogLevel.Warning));
        services.AddTimeFlowApplication();
        services.AddTimeFlowInfrastructure(config, new TestHostEnvironment(root), "LocalDemo");
        services.AddScoped<IRealtimeNotifier, NullRealtimeNotifier>();
        var provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        await provider.InitializeTimeFlowDatabaseAsync();
        return new TestDatabase(root, provider);
    }

    public AsyncServiceScope Scope() => Services.CreateAsyncScope();

    public async Task<T> RunAsync<T>(Func<IServiceProvider, Task<T>> work)
    {
        await using var scope = Scope();
        return await work(scope.ServiceProvider);
    }

    public async Task RunAsync(Func<IServiceProvider, Task> work)
    {
        await using var scope = Scope();
        await work(scope.ServiceProvider);
    }

    public Task<Actor> ActorAsync(string localPart) => RunAsync(async sp =>
    {
        var db = sp.GetRequiredService<ITimeFlowDbContext>();
        var email = $"{localPart}@{Domain}";
        var e = await db.Employees.AsNoTracking().Include(x => x.User).SingleAsync(x => x.NormalizedEmail == email);
        return new Actor(e.Id, e.FullName, e.User!.Roles, "127.0.0.1", "unit-tests");
    });

    public LocalClock Clock => Services.GetRequiredService<LocalClock>();

    public async ValueTask DisposeAsync()
    {
        await Services.DisposeAsync();
        SqliteConnection.ClearAllPools();
        try { Directory.Delete(Root, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }
}
