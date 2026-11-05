using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gpv.Sqi.Config;
using Gpv.Sqi.Data;
using Gpv.Sqi.Demo;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Services;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace Gpv.Sqi.Tests;

public static class TestHelpers
{
    static TestHelpers() { AppLog.Console = false; }

    public static string Fixtures => Path.Combine(AppContext.BaseDirectory, "fixtures");

    public static List<JsonObject> Fixture(string name) => Json.ParseRows(File.ReadAllText(Path.Combine(Fixtures, name)));
    public static List<JsonObject> Smt => Fixture("mirion_W07632100028_smt.json");
    public static List<JsonObject> Quality => Fixture("mirion_W07632100028_quality.json");
    public static List<JsonObject> History => Fixture("mirion_W07632100028_quality_history.json");
    public static byte[] MetadataBytes => File.ReadAllBytes(Path.Combine(Fixtures, "metadata_sample.xml"));

    public static string TempDb() => Path.Combine(Path.GetTempPath(), $"gpv_sqi_test_{Guid.NewGuid():N}.sqlite3");

    public static AppServices DemoServices()
    {
        AppLog.Console = false;
        return new AppServices(AppConfig.Defaults(), new Database(TempDb()), new DemoDataSource(Fixtures));
    }

    public static AppConfig LiveConfig(string baseUrl, Action<AppConfig>? tweak = null)
    {
        AppLog.Console = false;
        var cfg = AppConfig.Defaults();
        cfg.Set("mode", "live");
        cfg.Set("security.live_mode_approved", true);
        cfg.Set("odata.base_url", baseUrl);
        cfg.Set("odata.timeout_seconds", 2);
        cfg.Set("odata.backoff_seconds", 0.01);
        cfg.Set("odata.max_retries", 1);
        cfg.Set("odata.max_pages", 3);
        // Protección desactivada por defecto en las pruebas; ProtectionTests la activa explícitamente.
        cfg.Set("protection.cooldown_seconds", 0);
        cfg.Set("protection.result_cache_seconds", 0);
        cfg.Set("protection.min_interval_ms", 0);
        tweak?.Invoke(cfg);
        return cfg;
    }

    public static int FreePort()
    {
        var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        var port = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        return port;
    }
}

/// <summary>Comportamiento de una respuesta del servidor falso.</summary>
public sealed record Behavior(int Status = 200, object? Body = null, double Delay = 0, Dictionary<string, string>? Headers = null)
{
    public byte[] Bytes => Body switch
    {
        null => [],
        byte[] b => b,
        string s => Encoding.UTF8.GetBytes(s),
        _ => Encoding.UTF8.GetBytes(JsonSerializer.Serialize(Body)),
    };
}

/// <summary>Servidor HTTP falso que imita FactoryLogix OData (Kestrel local).</summary>
public sealed class FakeODataServer : IAsyncDisposable
{
    private readonly WebApplication _app;
    public Dictionary<string, List<Behavior>> Behaviors { get; } = new();
    public List<(string Path, Dictionary<string, string> Headers)> Requests { get; } = [];
    public int Port { get; }
    public string BaseUrl => $"http://127.0.0.1:{Port}/odata/";

    public FakeODataServer()
    {
        Port = TestHelpers.FreePort();
        var b = WebApplication.CreateSlimBuilder();
        b.Logging.ClearProviders();
        b.WebHost.UseKestrel(k => k.Listen(IPAddress.Loopback, Port));
        _app = b.Build();
        _app.Run(async http =>
        {
            var path = http.Request.Path.Value!.Split('/')[^1];
            lock (Requests)
                Requests.Add((http.Request.Path + http.Request.QueryString, http.Request.Headers.ToDictionary(h => h.Key, h => h.Value.ToString())));
            Behavior beh;
            lock (Behaviors)
            {
                var queue = Behaviors.GetValueOrDefault(path) ?? Behaviors.GetValueOrDefault("*") ?? [new Behavior(404)];
                beh = queue.Count > 1 ? queue[0] : queue[0];
                if (queue.Count > 1) queue.RemoveAt(0);
            }
            if (beh.Delay > 0)
            {
                try { await Task.Delay(TimeSpan.FromSeconds(beh.Delay), http.RequestAborted); }
                catch (OperationCanceledException) { return; }
            }
            http.Response.StatusCode = beh.Status;
            foreach (var (k, v) in beh.Headers ?? []) http.Response.Headers[k] = v;
            var bytes = beh.Bytes;
            http.Response.ContentLength = bytes.Length;
            await http.Response.Body.WriteAsync(bytes);
        });
        _app.StartAsync().GetAwaiter().GetResult();
    }

    public List<(string Path, Dictionary<string, string> Headers)> EntityRequests(string name)
    {
        lock (Requests) return Requests.Where(r => r.Path.Contains($"/{name}?")).ToList();
    }

    public async ValueTask DisposeAsync() => await _app.DisposeAsync();
}
