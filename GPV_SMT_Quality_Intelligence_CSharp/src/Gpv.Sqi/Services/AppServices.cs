using Gpv.Sqi.Config;
using Gpv.Sqi.Data;
using Gpv.Sqi.Demo;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;

namespace Gpv.Sqi.Services;

/// <summary>Contexto de aplicación: configuración vigente, fuente de datos activa y repositorios.</summary>
public sealed class AppServices
{
    private readonly object _gate = new();
    private readonly IDataSource _demo;
    private readonly Func<AppConfig, IDataSource> _liveFactory;
    private IDataSource _source = null!;

    public AppConfig BaseConfig { get; }
    public AppConfig Config { get; private set; } = null!;
    public Database Db { get; }
    public AuditRepository Audit { get; }
    public CacheRepository Cache { get; }
    public SettingsRepository Settings { get; }
    /// <summary>Protección compartida (caché, pausas, ritmo) que sobrevive a cambios de configuración.</summary>
    public ODataGuard Guard { get; } = new();

    public AppServices(AppConfig baseConfig, Database? db = null, IDataSource? demo = null, Func<AppConfig, IDataSource>? liveFactory = null)
    {
        BaseConfig = baseConfig;
        Db = db ?? new Database(baseConfig.ResolvePath("database"));
        Audit = new AuditRepository(Db);
        Cache = new CacheRepository(Db);
        Settings = new SettingsRepository(Db);
        _demo = demo ?? new DemoDataSource();
        _liveFactory = liveFactory ?? (cfg => new FactoryLogixODataClient(cfg, onResult: Audit.RecordQuery, guard: Guard));
        Reload();
    }

    public IDataSource Source { get { lock (_gate) return _source; } }

    public void Reload()
    {
        lock (_gate)
        {
            var old = _source;
            Config = BaseConfig.WithOverrides(Settings.All());
            _source = Config.Mode == "live" ? _liveFactory(Config) : _demo;
            if (old is IDisposable d && !ReferenceEquals(old, _source)) d.Dispose();
            AppLog.Info("context", $"Modo activo: {Config.Mode}");
        }
    }

    public string DataSource => Config.Mode == "live" ? "live" : "demo";

    /// <summary>Ejecuta una consulta; la auditoría del modo demo se registra aquí (el cliente real usa callback).</summary>
    public async Task<QueryResult> ExecuteAsync(QuerySpec spec, CancellationToken ct = default)
    {
        var result = await Source.ExecuteAsync(spec, ct);
        if (DataSource == "demo")
        {
            AppLog.Info("odata", $"ODATA-DEMO | {result.Entity} | {result.Status} | HTTP={result.HttpStatus?.ToString() ?? "None"} | {result.ElapsedMs:0} ms | filas={result.Rows.Count} | {result.QueryDescription} | {result.Error}");
            Audit.RecordQuery(result);
        }
        return result;
    }
}
