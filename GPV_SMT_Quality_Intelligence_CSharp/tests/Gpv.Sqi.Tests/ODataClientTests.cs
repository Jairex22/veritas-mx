using System.Text;
using Gpv.Sqi.Config;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;
using Gpv.Sqi.OData;
using Xunit;

namespace Gpv.Sqi.Tests;

/// <summary>Cliente OData contra un servidor HTTP falso (sin red real).</summary>
public class ODataClientTests : IAsyncLifetime
{
    private static readonly QuerySpec Spec = new("SMT", [new Filter("Identifier", "eq", "W07632100028")], [("EventDate", "asc")], 50);
    private FakeODataServer _srv = null!;
    private readonly List<QueryResult> _results = [];

    public Task InitializeAsync()
    {
        _srv = new FakeODataServer();
        _srv.Behaviors["$metadata"] = [new Behavior(200, TestHelpers.MetadataBytes)];
        return Task.CompletedTask;
    }

    public async Task DisposeAsync() => await _srv.DisposeAsync();

    private FactoryLogixODataClient Client(Credential? cred = null, Action<AppConfig>? tweak = null) =>
        new(TestHelpers.LiveConfig(_srv.BaseUrl, tweak), _ => cred, _results.Add);

    private static object Value(params object[] rows) => new Dictionary<string, object> { ["value"] = rows };

    [Fact]
    public async Task OkWithRows()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, Encoding.UTF8.GetBytes("{\"value\":" + System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(Path.Combine(TestHelpers.Fixtures, "mirion_W07632100028_smt.json")))!["value"]!.ToJsonString() + "}"))];
        var r = await Client().ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.OK, r.Status);
        Assert.Equal(4, r.Rows.Count);
        Assert.Equal(200, r.HttpStatus);
        Assert.True(r.ElapsedMs > 0);
        Assert.Contains("wait_headers_ms", r.Timings.Keys);
        Assert.Contains("parse_ms", r.Timings.Keys);
    }

    [Fact]
    public async Task EmptyIsDistinctFromError()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, Value())];
        var r = await Client().ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.EMPTY, r.Status);
        Assert.True(r.Ok);
    }

    [Theory]
    [InlineData(401, ODataStatus.AUTH_ERROR)]
    [InlineData(403, ODataStatus.FORBIDDEN)]
    public async Task AuthErrorsNotRetried(int code, ODataStatus expected)
    {
        _srv.Behaviors["SMT"] = [new Behavior(code)];
        var r = await Client(tweak: c => c.Set("odata.max_retries", 2)).ExecuteAsync(Spec);
        Assert.Equal(expected, r.Status);
        Assert.Single(_srv.EntityRequests("SMT"));
        Assert.False(r.Ok);
    }

    [Fact]
    public async Task NotFound404()
    {
        _srv.Behaviors["SMT"] = [new Behavior(404)];
        Assert.Equal(ODataStatus.NOT_FOUND, (await Client().ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task Server500RetriedWithBackoffThenFails()
    {
        _srv.Behaviors["SMT"] = [new Behavior(500, "boom")];
        var r = await Client().ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.SERVER_ERROR, r.Status);
        Assert.Equal(2, _srv.EntityRequests("SMT").Count);
        Assert.Equal(2, r.Attempts);
        Assert.Empty(r.Rows);
    }

    [Fact]
    public async Task Server503ThenSuccess()
    {
        _srv.Behaviors["SMT"] = [new Behavior(503), new Behavior(200, Value(new { Identifier = "X" }))];
        var r = await Client().ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.OK, r.Status);
        Assert.Equal(2, r.Attempts);
    }

    [Fact]
    public async Task RateLimited429()
    {
        _srv.Behaviors["SMT"] = [new Behavior(429, Headers: new() { ["Retry-After"] = "0" })];
        Assert.Equal(ODataStatus.RATE_LIMITED, (await Client(tweak: c => c.Set("odata.max_retries", 0)).ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task TimeoutNotRetried()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, Value(), Delay: 1.5)];
        var r = await Client(tweak: c => { c.Set("odata.timeout_seconds", 0.4); c.Set("odata.max_retries", 2); }).ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.TIMEOUT, r.Status);
        Assert.Equal(1, r.Attempts);
        Assert.False(r.Ok);
    }

    [Fact]
    public async Task ConnectionRefused()
    {
        var port = TestHelpers.FreePort();
        var c = new FactoryLogixODataClient(TestHelpers.LiveConfig($"http://127.0.0.1:{port}/odata/"), _ => null);
        var r = await c.ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.CONNECTION_ERROR, r.Status);
    }

    [Fact]
    public async Task DnsFailure()
    {
        var c = new FactoryLogixODataClient(TestHelpers.LiveConfig("http://nonexistent-host.invalid:6065/odata/"), _ => null);
        Assert.Equal(ODataStatus.CONNECTION_ERROR, (await c.ExecuteAsync(Spec)).Status);
    }

    [Theory]
    [InlineData("<html>500</html>")]
    [InlineData("{\"items\": []}")]
    [InlineData("{\"value\": \"x\"}")]
    public async Task InvalidJsonAndStructure(string body)
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, body)];
        var r = await Client().ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.INVALID_RESPONSE, r.Status);
        Assert.Empty(r.Rows);
    }

    [Fact]
    public async Task RedirectNotFollowed()
    {
        _srv.Behaviors["SMT"] = [new Behavior(302, Headers: new() { ["Location"] = "http://evil.invalid/" })];
        Assert.Equal(ODataStatus.HTTP_ERROR, (await Client().ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task PolicyBlocks()
    {
        var notApproved = TestHelpers.LiveConfig(_srv.BaseUrl, c => c.Set("security.live_mode_approved", false));
        Assert.Equal(ODataStatus.BLOCKED_BY_POLICY, (await new FactoryLogixODataClient(notApproved).ExecuteAsync(Spec)).Status);
        var basicHttp = TestHelpers.LiveConfig(_srv.BaseUrl, c => c.Set("odata.auth_method", "basic"));
        Assert.Equal(ODataStatus.BLOCKED_BY_POLICY, (await new FactoryLogixODataClient(basicHttp, _ => new Credential("u", "p")).ExecuteAsync(Spec)).Status);
        var demo = TestHelpers.LiveConfig(_srv.BaseUrl, c => c.Set("mode", "demo"));
        Assert.Equal(ODataStatus.BLOCKED_BY_POLICY, (await new FactoryLogixODataClient(demo).ExecuteAsync(Spec)).Status);
        Assert.Empty(_srv.EntityRequests("SMT"));
    }

    [Fact]
    public async Task MissingCredentials()
    {
        var cfg = TestHelpers.LiveConfig(_srv.BaseUrl, c => { c.Set("odata.auth_method", "basic"); c.Set("security.allow_basic_auth_over_http", true); });
        Assert.Equal(ODataStatus.NOT_CONFIGURED, (await new FactoryLogixODataClient(cfg, _ => null).ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task BasicAuthHeaderSentAndNotLogged()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, Value())];
        var lines = new List<string>();
        void Capture(string l) { lock (lines) lines.Add(l); }
        AppLog.LineWritten += Capture;
        try
        {
            var cred = new Credential("42178", "S3cr3t!");
            var cfg = TestHelpers.LiveConfig(_srv.BaseUrl, c => { c.Set("odata.auth_method", "basic"); c.Set("security.allow_basic_auth_over_http", true); });
            var r = await new FactoryLogixODataClient(cfg, _ => cred).ExecuteAsync(Spec);
            Assert.Equal(ODataStatus.EMPTY, r.Status);
            Assert.StartsWith("Basic ", _srv.EntityRequests("SMT")[0].Headers["Authorization"]);
            Assert.DoesNotContain("S3cr3t", cred.ToString());
        }
        finally { AppLog.LineWritten -= Capture; }
        var all = string.Join("\n", lines);
        Assert.DoesNotContain("S3cr3t!", all);
        Assert.DoesNotContain("Authorization", all);
    }

    [Fact]
    public async Task NoAuthHeaderWhenNone()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, Value())];
        await Client().ExecuteAsync(Spec);
        Assert.DoesNotContain("Authorization", _srv.EntityRequests("SMT")[0].Headers.Keys);
    }

    [Fact]
    public async Task EntityMissingInMetadata()
    {
        var xml = Encoding.UTF8.GetString(TestHelpers.MetadataBytes).Replace("<EntitySet Name=\"SMT\"", "<EntitySet Name=\"SMTX\"");
        _srv.Behaviors["$metadata"] = [new Behavior(200, xml)];
        Assert.Equal(ODataStatus.NOT_FOUND, (await Client().ExecuteAsync(Spec)).Status);
    }

    [Fact]
    public async Task MetadataFailureFallsBackAndMarksUnverified()
    {
        _srv.Behaviors["$metadata"] = [new Behavior(500)];
        _srv.Behaviors["SMT"] = [new Behavior(200, Value())];
        var r = await Client(tweak: c => c.Set("odata.max_retries", 0)).ExecuteAsync(Spec);
        Assert.Equal(ODataStatus.EMPTY, r.Status);
        Assert.Contains("tipos no verificados", r.QueryDescription);
    }

    [Fact]
    public async Task PaginationSameOrigin()
    {
        var next = _srv.BaseUrl + "SMT?$skiptoken=2";
        _srv.Behaviors["SMT"] = [
            new Behavior(200, new Dictionary<string, object> { ["value"] = new[] { new { Identifier = "A" } }, ["@odata.nextLink"] = next }),
            new Behavior(200, Value(new { Identifier = "B" })),
        ];
        var r = await Client().ExecuteAsync(Spec);
        Assert.Equal(["A", "B"], r.Rows.Select(x => x.Str("Identifier")));
    }

    [Fact]
    public async Task PaginationForeignOriginIgnored()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, new Dictionary<string, object> { ["value"] = new[] { new { Identifier = "A" } }, ["@odata.nextLink"] = "http://evil.invalid/SMT" })];
        var r = await Client().ExecuteAsync(Spec);
        Assert.Single(r.Rows);
        Assert.True(r.Truncated);
    }

    [Fact]
    public async Task ResultsEmittedForAudit()
    {
        _srv.Behaviors["SMT"] = [new Behavior(500)];
        await Client(tweak: c => c.Set("odata.max_retries", 0)).ExecuteAsync(Spec);
        Assert.Contains(_results, x => x.Entity == "SMT" && x.Status == ODataStatus.SERVER_ERROR);
    }

    [Fact]
    public async Task ConcurrencyLimitSerializesRequests()
    {
        _srv.Behaviors["SMT"] = [new Behavior(200, Value(), Delay: 0.3)];
        var client = Client();
        var sw = System.Diagnostics.Stopwatch.StartNew();
        await Task.WhenAll(client.ExecuteAsync(Spec), client.ExecuteAsync(Spec), client.ExecuteAsync(Spec));
        Assert.True(sw.Elapsed.TotalSeconds >= 0.85, $"Con límite 1 deben ejecutarse en serie ({sw.Elapsed.TotalSeconds:0.00}s)");
    }
}
