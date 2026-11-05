using System.Text.Json.Nodes;
using Gpv.Sqi.Api;
using Gpv.Sqi.Config;
using Gpv.Sqi.Data;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;
using Gpv.Sqi.Services;
using Xunit;

namespace Gpv.Sqi.Tests;

/// <summary>Medidas para no sobrecargar FactoryLogix.</summary>
public class ProtectionTests : IAsyncLifetime
{
    private static readonly QuerySpec Spec = new("SMT", [new Filter("Identifier", "eq", "W07632100028")], top: 50);
    private FakeODataServer _srv = null!;

    public Task InitializeAsync()
    {
        _srv = new FakeODataServer();
        _srv.Behaviors["$metadata"] = [new Behavior(200, TestHelpers.MetadataBytes)];
        return Task.CompletedTask;
    }

    public async Task DisposeAsync() => await _srv.DisposeAsync();

    private FactoryLogixODataClient Client(Action<AppConfig> tweak, ODataGuard? guard = null) =>
        new(TestHelpers.LiveConfig(_srv.BaseUrl, tweak), _ => null, guard: guard);

    [Fact]
    public void Defaults()
    {
        var cfg = AppConfig.Defaults();
        Assert.Equal(0, cfg.Int("odata.max_retries"));        // un 500 lento no se repite
        Assert.Equal(1, cfg.Int("odata.max_pages"));
        Assert.Equal(60, cfg.Int("protection.cooldown_seconds"));
        Assert.Equal(60, cfg.Int("protection.result_cache_seconds"));
        Assert.Equal(1000, cfg.Int("protection.min_interval_ms"));
        Assert.True(cfg.Int("pulse.max_events") <= 200);
        Assert.True(cfg.Int("quality.max_defects") <= 200);
    }

    [Fact]
    public async Task SameQueryReusedFromCache()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, "{\"value\":[{\"Identifier\":\"A\"}]}")];
        var c = Client(cfg => cfg.Set("protection.result_cache_seconds", 60));
        var first = await c.ExecuteAsync(Spec);
        var second = await c.ExecuteAsync(Spec);
        Assert.Single(_srv.EntityRequests("SMT"));
        Assert.Equal(ODataStatus.OK, second.Status);
        Assert.Equal(0, second.Attempts);
        Assert.Contains("reutilizada", second.QueryDescription);
        Assert.Equal(first.Rows[0].ToJsonString(), second.Rows[0].ToJsonString());
    }

    [Fact]
    public async Task FailurePausesEntity()
    {
        _srv.Behaviors["SMT"] = [new Behavior(500)];
        _srv.Behaviors["Quality"] = [new Behavior(200, "{\"value\":[]}")];
        var c = Client(cfg => { cfg.Set("protection.cooldown_seconds", 60); cfg.Set("odata.max_retries", 0); });
        Assert.Equal(ODataStatus.SERVER_ERROR, (await c.ExecuteAsync(Spec)).Status);
        var paused = await c.ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.COOLDOWN, paused.Status);
        Assert.False(paused.Ok);                                 // nunca se interpreta como "sin registros"
        Assert.Single(_srv.EntityRequests("SMT"));               // la segunda no llegó a FactoryLogix
        var other = await c.ExecuteAsync(new QuerySpec("Quality", [new Filter("Identifier", "eq", "X")], top: 5));
        Assert.Equal(ODataStatus.EMPTY, other.Status);           // otras entidades siguen disponibles
    }

    [Fact]
    public async Task TimeoutPausesEntity()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, "{\"value\":[]}", Delay: 1.0)];
        var c = Client(cfg => { cfg.Set("protection.cooldown_seconds", 60); cfg.Set("odata.timeout_seconds", 0.3); });
        Assert.Equal(ODataStatus.TIMEOUT, (await c.ExecuteAsync(Spec)).Status);
        Assert.Equal(ODataStatus.COOLDOWN, (await c.ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task AuthErrorDoesNotPause()
    {
        _srv.Behaviors["SMT"] = [new Behavior(401)];
        var c = Client(cfg => cfg.Set("protection.cooldown_seconds", 60));
        await c.ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.AUTH_ERROR, (await c.ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task GuardSharedAcrossClients()
    {
        _srv.Behaviors["SMT"] = [new Behavior(500)];
        var guard = new ODataGuard();
        await Client(cfg => { cfg.Set("protection.cooldown_seconds", 60); cfg.Set("odata.max_retries", 0); }, guard).ExecuteAsync(Spec);
        // Un cliente nuevo (p. ej. tras guardar la configuración) respeta la pausa.
        Assert.Equal(ODataStatus.COOLDOWN, (await Client(cfg => cfg.Set("protection.cooldown_seconds", 60), guard).ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task MinIntervalSpacesRequests()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, "{\"value\":[]}")];
        var c = Client(cfg => cfg.Set("protection.min_interval_ms", 400));
        var sw = System.Diagnostics.Stopwatch.StartNew();
        await c.ExecuteAsync(new QuerySpec("SMT", [new Filter("Identifier", "eq", "A")], top: 1));
        await c.ExecuteAsync(new QuerySpec("SMT", [new Filter("Identifier", "eq", "B")], top: 1));
        Assert.True(sw.Elapsed.TotalMilliseconds >= 380, $"{sw.Elapsed.TotalMilliseconds:0} ms");
    }

    [Fact]
    public async Task SelectSentWithKnownColumnsOnly()
    {
        _srv.Behaviors["Quality"] = [new Behavior(200, "{\"value\":[]}")];
        await Client(_ => { }).ExecuteAsync(new QuerySpec("Quality", [new Filter("Identifier", "eq", "X")], top: 5));
        var path = Uri.UnescapeDataString(_srv.EntityRequests("Quality")[0].Path);
        Assert.Contains("$select=", path);
        Assert.Contains("DefectID", path);
        Assert.DoesNotContain("BatchQuantity", path);          // columnas no usadas no se piden
        Assert.DoesNotContain("$orderby", path);
    }

    [Fact]
    public async Task SelectCanBeDisabled()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, "{\"value\":[]}")];
        await Client(cfg => cfg.Set("odata.use_select", false)).ExecuteAsync(Spec);
        Assert.DoesNotContain("$select", Uri.UnescapeDataString(_srv.EntityRequests("SMT")[0].Path));
    }

    [Fact]
    public async Task TraceSendsNoOrderByAndSortsLocally()
    {
        var rows = TestHelpers.Smt.AsEnumerable().Reverse().Select(r => r.ToJsonString());
        _srv.Behaviors["SMT"] = [new Behavior(200, "{\"value\":[" + string.Join(",", rows) + "]}")];
        _srv.Behaviors["Quality"] = [new Behavior(200, "{\"value\":[]}")];
        var cfg = TestHelpers.LiveConfig(_srv.BaseUrl);
        var ctx = new AppServices(cfg, new Database(TestHelpers.TempDb()), liveFactory: c => new FactoryLogixODataClient(c, _ => null));
        var t = (Dictionary<string, object?>)await new ApiHandlers(ctx).TraceAsync(new JsonObject { ["identifier"] = "W07632100028" }, default);
        Assert.All(_srv.Requests.Where(r => !r.Path.Contains("$metadata")), r => Assert.DoesNotContain("orderby", Uri.UnescapeDataString(r.Path)));
        var events = (List<JsonObject>)t["smt_events"]!;
        Assert.Equal("SMT Post-Reflow AOI Top", events[0]["OperationName"]!.GetValue<string>());
        Assert.Equal("QA SMT", events[^1]["OperationName"]!.GetValue<string>());
    }
}
