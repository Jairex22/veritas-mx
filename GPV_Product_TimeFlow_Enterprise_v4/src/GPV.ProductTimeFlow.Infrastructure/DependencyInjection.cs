using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure.Documents;
using GPV.ProductTimeFlow.Infrastructure.Email;
using GPV.ProductTimeFlow.Infrastructure.Persistence;
using GPV.ProductTimeFlow.Infrastructure.Seeding;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace GPV.ProductTimeFlow.Infrastructure;

public sealed class DatabaseOptions
{
    public const string Section = "Database";
    /// <summary>"Sqlite" (desarrollo y DEMO) o "SqlServer" (producción).</summary>
    public string Provider { get; set; } = "Sqlite";
    /// <summary>Si se omite con SQLite, se usa {DataRoot}/timeflow.db.</summary>
    public string? ConnectionString { get; set; }
    /// <summary>Aplicar migraciones al iniciar. En producción se recomienda false y usar el script idempotente.</summary>
    public bool AutoMigrate { get; set; } = true;
}

public static class InfrastructureRegistration
{
    /// <summary>Resuelve la carpeta de datos (BD SQLite, adjuntos, buzón DEMO, llaves) relativa a la raíz de contenido.</summary>
    public static string ResolveDataRoot(IConfiguration config, string contentRoot)
    {
        var configured = config["TimeFlow:DataRoot"] ?? "App_Data";
        var path = Path.IsPathRooted(configured) ? configured : Path.GetFullPath(Path.Combine(contentRoot, configured));
        Directory.CreateDirectory(path);
        return path;
    }

    public static IServiceCollection AddTimeFlowInfrastructure(this IServiceCollection services, IConfiguration config, IHostEnvironment env, string authenticationMode)
    {
        var dataRoot = ResolveDataRoot(config, env.ContentRootPath);
        services.Configure<TimeFlowOptions>(config.GetSection(TimeFlowOptions.Section));
        services.Configure<DemoOptions>(config.GetSection(DemoOptions.Section));
        services.Configure<EmailOptions>(config.GetSection(EmailOptions.Section));
        services.PostConfigure<EmailOptions>(o => { if (!Path.IsPathRooted(o.MockDropFolder)) o.MockDropFolder = Path.Combine(dataRoot, "mail-drop"); });
        services.Configure<StorageOptions>(o => o.AttachmentsRoot = config["TimeFlow:AttachmentsPath"] is { Length: > 0 } p && Path.IsPathRooted(p) ? p : Path.Combine(dataRoot, "attachments"));
        services.Configure<DatabaseOptions>(config.GetSection(DatabaseOptions.Section));

        var db = config.GetSection(DatabaseOptions.Section).Get<DatabaseOptions>() ?? new DatabaseOptions();
        if (db.Provider.Equals("SqlServer", StringComparison.OrdinalIgnoreCase))
        {
            var cs = db.ConnectionString ?? throw new InvalidOperationException("Database:ConnectionString es obligatorio para SQL Server (use variable de entorno Database__ConnectionString).");
            services.AddDbContext<TimeFlowDbContext, SqlServerTimeFlowDbContext>(o => o.UseSqlServer(cs, s => s.MigrationsHistoryTable("__EFMigrationsHistory", "dbo")));
        }
        else
        {
            var cs = db.ConnectionString ?? $"Data Source={Path.Combine(dataRoot, "timeflow.db")};Default Timeout=30";
            services.AddDbContext<TimeFlowDbContext, SqliteTimeFlowDbContext>(o => o.UseSqlite(cs).AddInterceptors(new SqlitePragmaInterceptor()));
        }
        services.AddScoped<ITimeFlowDbContext>(sp => sp.GetRequiredService<TimeFlowDbContext>());

        services.AddSingleton<IPasswordService, PasswordService>();
        services.AddSingleton<IFileStorage, LocalFileStorage>();
        services.AddSingleton<IPdfRenderer, PdfRenderer>();
        services.AddSingleton<IExcelExporter, ExcelExporter>();
        services.AddSingleton<IExcelImporter, ExcelImporter>();
        services.AddSingleton<IQrCodeGenerator, QrCodeGeneratorService>();
        services.AddSingleton<IEmailComposer, EmailComposer>();
        services.AddSingleton<InProcessNotificationBus>();
        services.AddScoped<IRealtimeNotifier, RealtimeNotifier>();
        services.AddSingleton<DataSeeder>();

        var email = config.GetSection(EmailOptions.Section).Get<EmailOptions>() ?? new EmailOptions();
        var graph = email.Provider.Equals("Graph", StringComparison.OrdinalIgnoreCase);
        if (graph) services.AddSingleton<IEmailSender, GraphEmailSender>();
        else services.AddSingleton<IEmailSender, MockEmailSender>();
        services.AddSingleton(new IntegrationStatus(graph ? "Microsoft Graph (envío real)" : "Mock (DEMO: no envía correos)", authenticationMode));
        services.AddSingleton<EmailOutboxProcessor>();
        services.AddHostedService(sp => sp.GetRequiredService<EmailOutboxProcessor>());
        services.AddHostedService<ReminderBackgroundService>();
        return services;
    }

    /// <summary>
    /// Validación de arranque que impide mezclar ambientes: PRODUCCIÓN exige SQL Server, Microsoft Graph y Entra ID.
    /// </summary>
    public static void ValidateEnvironment(IConfiguration config, string authenticationMode)
    {
        var options = config.GetSection(TimeFlowOptions.Section).Get<TimeFlowOptions>() ?? new TimeFlowOptions();
        if (options.Mode != EnvironmentMode.Production) return;
        var errors = new List<string>();
        if (!string.Equals(config["Database:Provider"], "SqlServer", StringComparison.OrdinalIgnoreCase)) errors.Add("PRODUCCIÓN requiere Database:Provider = SqlServer.");
        if (!string.Equals(config["Email:Provider"], "Graph", StringComparison.OrdinalIgnoreCase)) errors.Add("PRODUCCIÓN requiere Email:Provider = Graph.");
        if (!string.Equals(authenticationMode, "EntraId", StringComparison.OrdinalIgnoreCase)) errors.Add("PRODUCCIÓN requiere Authentication:Mode = EntraId (sin cuentas locales DEMO).");
        if (!options.PublicBaseUrl.StartsWith("https://", StringComparison.OrdinalIgnoreCase) || options.PublicBaseUrl.Contains("localhost")) errors.Add("PRODUCCIÓN requiere TimeFlow:PublicBaseUrl con HTTPS y el dominio corporativo.");
        if (errors.Count > 0) throw new InvalidOperationException("Configuración de PRODUCCIÓN inválida:\n - " + string.Join("\n - ", errors));
    }

    public static async Task InitializeTimeFlowDatabaseAsync(this IServiceProvider services, CancellationToken ct = default)
    {
        using var scope = services.CreateScope();
        var sp = scope.ServiceProvider;
        var logger = sp.GetRequiredService<ILoggerFactory>().CreateLogger("TimeFlow.Database");
        var options = sp.GetRequiredService<IOptions<TimeFlowOptions>>().Value;
        var dbOptions = sp.GetRequiredService<IOptions<DatabaseOptions>>().Value;
        var context = sp.GetRequiredService<TimeFlowDbContext>();
        if (dbOptions.AutoMigrate)
        {
            logger.LogInformation("Aplicando migraciones ({Provider})…", context.ProviderName);
            await context.Database.MigrateAsync(ct);
        }
        var seeder = sp.GetRequiredService<DataSeeder>();
        await seeder.SeedReferenceDataAsync(ct);
        if (options.Mode == EnvironmentMode.Demo) await seeder.SeedDemoAsync(ct);
    }
}
