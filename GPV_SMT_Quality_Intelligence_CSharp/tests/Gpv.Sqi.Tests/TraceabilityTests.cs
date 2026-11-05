using System.Text.Json.Nodes;
using Gpv.Sqi.Api;
using Gpv.Sqi.Data;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.OData;
using Gpv.Sqi.Services;
using Xunit;

namespace Gpv.Sqi.Tests;

public class MirionAcceptanceTests
{
    private static readonly Lazy<(ApiHandlers Api, Dictionary<string, object?> Trace)> Data = new(() =>
    {
        var api = new ApiHandlers(TestHelpers.DemoServices());
        var t = (Dictionary<string, object?>)api.TraceAsync(new JsonObject { ["identifier"] = "W07632100028" }, default).Result;
        return (api, t);
    });
    private static Dictionary<string, object?> T => Data.Value.Trace;
    private static Dictionary<string, object?> D(object? o) => (Dictionary<string, object?>)o!;

    [Fact]
    public void MergedSources()
    {
        foreach (var name in new[] { "SMT", "Quality", "QualityHistory" })
            Assert.Equal("OK", ((Dictionary<string, Dictionary<string, object?>>)T["sources"]!)[name]["status"]);
        Assert.Equal("FOUND", T["state"]);
        Assert.Equal(true, T["is_demo"]);
    }

    [Fact]
    public void Header()
    {
        var h = D(T["header"]);
        Assert.Equal("Mirion Technologies (Canberra) Inc.", h["customer"]);
        Assert.Equal("MR.48.SM", h["assembly"]);
        Assert.Equal("W076321", h["batch"]);
        Assert.Equal("5066049", h["lot"]);
        Assert.Equal(false, h["line_verified"]);
    }

    [Fact]
    public void FodOnceAoiNotTwoBoards()
    {
        var s = D(T["summary"]);
        Assert.Equal(1, s["unique_defects"]);
        Assert.Equal(4, s["smt_events"]);
        Assert.Equal(3, s["history_entries"]);
        var aoi = ((List<Dictionary<string, object?>>)s["operations"]!).First(o => (string)o["operation"]! == "SMT Post-Reflow AOI Top");
        Assert.Equal(2, aoi["count"]);
        Assert.Contains("tarjetas diferentes", string.Join(" ", (List<string>)D(T["evidence"])["unverifiable"]!));
    }

    [Fact]
    public void RepairAndClosedShown()
    {
        Assert.Contains("SMT REPAIR", ((List<Dictionary<string, object?>>)D(T["summary"])["operations"]!).Select(o => o["operation"]));
        Assert.Equal("Closed", ((List<Dictionary<string, object?>>)T["defects"]!)[0]["status"]);
        Assert.Contains((List<Dictionary<string, object?>>)T["timeline"]!, e => (string)e["kind"]! == "DEFECT_HISTORY" && ((string)e["title"]!).Contains("Closed"));
    }

    [Fact]
    public void NeverPass()
    {
        Assert.Equal("NO_VERIFICABLE", D(T["summary"])["final_result"]);
        Assert.DoesNotContain("\"PASS\"", Json.Serialize(T));
        Assert.Contains("El cierre de un defecto no constituye", (string)T["disclaimer"]!);
    }

    [Fact]
    public async Task ReportGenerated()
    {
        var (data, _, name) = await Data.Value.Api.ReportAsync(new JsonObject { ["identifier"] = "W07632100028", ["format"] = "csv" }, default);
        Assert.StartsWith("DEMO_", name);
        Assert.Contains("El cierre de un defecto no constituye", System.Text.Encoding.UTF8.GetString(data));
    }
}

public class FailureModeTests
{
    private static async Task<Dictionary<string, object?>> Trace(string id, AppServices? ctx = null) =>
        (Dictionary<string, object?>)await new ApiHandlers(ctx ?? TestHelpers.DemoServices()).TraceAsync(new JsonObject { ["identifier"] = id }, default);

    private static Dictionary<string, Dictionary<string, object?>> Sources(Dictionary<string, object?> t) =>
        (Dictionary<string, Dictionary<string, object?>>)t["sources"]!;

    [Fact]
    public async Task QualityHistoryFailureDoesNotHideSmt()
    {
        var t = await Trace("DEMO-QH-FAIL");
        Assert.Equal("OK", Sources(t)["SMT"]["status"]);
        Assert.Equal("TIMEOUT", Sources(t)["QualityHistory"]["status"]);
        Assert.Equal(4, ((Dictionary<string, object?>)t["summary"]!)["smt_events"]);
        Assert.Equal("HISTORY_INCOMPLETE", ((List<Dictionary<string, object?>>)t["defects"]!)[0]["classification"]);
        Assert.Contains((List<string>)((Dictionary<string, object?>)t["evidence"]!)["unverifiable"]!, x => x.Contains("QualityHistory no respondió"));
    }

    [Theory]
    [InlineData("DEMO-ERR-401")]
    [InlineData("DEMO-ERR-403")]
    [InlineData("DEMO-ERR-500")]
    [InlineData("DEMO-TIMEOUT")]
    [InlineData("DEMO-INVALID-JSON")]
    public async Task AllSourcesFailIsErrorNotEmpty(string id) => Assert.Equal("ERROR", (await Trace(id))["state"]);

    [Fact]
    public async Task EmptyIsNotFound()
    {
        var t = await Trace("NOEXISTE123");
        Assert.Equal("NOT_FOUND", t["state"]);
        Assert.Equal("NOT_REQUESTED", Sources(t)["QualityHistory"]["status"]);
    }

    [Fact]
    public async Task TimeoutUsesLastValidCacheMarkedStale()
    {
        await using var srv = new FakeODataServer();
        srv.Behaviors["$metadata"] = [new Behavior(200, TestHelpers.MetadataBytes)];
        var smtJson = "{\"value\":" + JsonNode.Parse(File.ReadAllText(Path.Combine(TestHelpers.Fixtures, "mirion_W07632100028_smt.json")))!["value"]!.ToJsonString() + "}";
        srv.Behaviors["SMT"] = [new Behavior(200, smtJson), new Behavior(200, "{\"value\":[]}", Delay: 1.2)];
        srv.Behaviors["Quality"] = [new Behavior(200, "{\"value\":[]}")];
        var cfg = TestHelpers.LiveConfig(srv.BaseUrl, c => { c.Set("odata.timeout_seconds", 0.4); c.Set("odata.max_retries", 0); });
        var ctx = new AppServices(cfg, new Database(TestHelpers.TempDb()), liveFactory: c => new FactoryLogixODataClient(c, _ => null));
        var first = await Trace("W07632100028", ctx);
        Assert.Equal("OK", Sources(first)["SMT"]["status"]);
        var second = await Trace("W07632100028", ctx);
        Assert.Equal("TIMEOUT", Sources(second)["SMT"]["status"]);
        Assert.Equal(true, Sources(second)["SMT"]["stale"]);
        Assert.Equal(4, ((Dictionary<string, object?>)second["summary"]!)["smt_events"]);
        Assert.Equal("live", second["data_source"]);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("A'B")]
    [InlineData("A B")]
    [InlineData("<script>")]
    [InlineData("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")]
    public async Task InvalidIdentifierRejected(string bad) =>
        await Assert.ThrowsAsync<InputException>(() => new ApiHandlers(TestHelpers.DemoServices()).TraceAsync(new JsonObject { ["identifier"] = bad }, default));

    [Fact]
    public async Task NonStringIdentifierRejected()
    {
        var api = new ApiHandlers(TestHelpers.DemoServices());
        await Assert.ThrowsAsync<InputException>(() => api.TraceAsync(new JsonObject { ["identifier"] = 123 }, default));
        await Assert.ThrowsAsync<InputException>(() => api.TraceAsync(new JsonObject(), default));
    }
}

public class ModulesDemoTests
{
    private readonly ApiHandlers _api = new(TestHelpers.DemoServices());
    private static Dictionary<string, object?> D(object o) => (Dictionary<string, object?>)o;

    [Fact]
    public async Task PulseExcludesHistoricalFixture()
    {
        var p = D(await _api.PulseAsync(new JsonObject { ["window"] = "4h" }, default));
        var k = D(p["kpis"]!);
        Assert.Equal(true, p["is_demo"]);
        Assert.True((int)k["events"]! > 0);
        Assert.DoesNotContain("W07632100028", ((List<JsonObject>)p["events"]!).Select(e => e.Str("Identifier")));
        Assert.Equal(false, D(p["line_filter"]!)["available"]);
        Assert.True((int)k["unique_identifiers"]! <= (int)k["events"]!);
    }

    [Fact]
    public async Task PulseFilterAndShiftErrors()
    {
        var p = D(await _api.PulseAsync(new JsonObject { ["window"] = "4h", ["customer"] = "DEMO Cliente A" }, default));
        Assert.Equal(["DEMO Cliente A"], ((List<JsonObject>)p["events"]!).Select(e => e.Str("Customer")).Distinct());
        await Assert.ThrowsAsync<InputException>(() => _api.PulseAsync(new JsonObject { ["window"] = "shift" }, default));
        await Assert.ThrowsAsync<InputException>(() => _api.PulseAsync(new JsonObject { ["window"] = "bogus" }, default));
    }

    [Fact]
    public async Task QualityUniqueDefects()
    {
        var q = D(await _api.QualityAsync(new JsonObject { ["window"] = "24h" }, default));
        var ids = ((List<Dictionary<string, object?>>)q["defects"]!).Select(d => (string)d["defect_id"]!).ToList();
        Assert.Equal(ids.Count, ids.Distinct().Count());
        Assert.Equal(ids.Count, D(q["summary"]!)["unique_defects"]);
        var ct = D(await _api.QualityCloseTimesAsync(new JsonObject { ["defect_ids"] = new JsonArray(ids.Select(i => (JsonNode?)JsonValue.Create(i)).ToArray()) }, default));
        Assert.Contains((List<Dictionary<string, object?>>)ct["defects"]!, d => d["time_to_close_min"] is not null);
    }

    [Fact]
    public async Task ReworkBatch()
    {
        var r = D(await _api.ReworkAsync(new JsonObject { ["batch"] = "DEMO-B300" }, default));
        Assert.True((int)r["units_observed"]! > 0);
        Assert.All((List<object>)r["units"]!, u => Assert.NotEmpty((List<Dictionary<string, object?>>)D(u)["alerts"]!));
    }
}
