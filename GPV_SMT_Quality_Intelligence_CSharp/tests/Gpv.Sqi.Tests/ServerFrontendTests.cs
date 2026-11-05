using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Gpv.Sqi.Api;
using Microsoft.AspNetCore.Builder;
using Xunit;

namespace Gpv.Sqi.Tests;

public sealed class ServerFixture : IAsyncLifetime
{
    public WebApplication App { get; private set; } = null!;
    public int Port { get; private set; }
    public string Token { get; private set; } = "";

    public async Task InitializeAsync()
    {
        Port = TestHelpers.FreePort();
        App = WebServer.Build(TestHelpers.DemoServices(), "127.0.0.1", Port);
        await App.StartAsync();
        using var c = new HttpClient();
        var html = await c.GetStringAsync($"http://127.0.0.1:{Port}/");
        Token = Regex.Match(html, "name=\"csrf-token\" content=\"([^\"]+)\"").Groups[1].Value;
    }

    public async Task DisposeAsync() => await App.DisposeAsync();
}

public class ServerTests(ServerFixture f) : IClassFixture<ServerFixture>
{
    private async Task<(HttpStatusCode Status, HttpResponseMessage Resp, byte[] Body)> Req(HttpMethod method, string path, object? body = null,
        bool auth = true, string? host = null, Dictionary<string, string>? headers = null, string contentType = "application/json")
    {
        using var handler = new SocketsHttpHandler { UseProxy = false };
        using var c = new HttpClient(handler);
        using var req = new HttpRequestMessage(method, $"http://127.0.0.1:{f.Port}{path}");
        if (host is not null) req.Headers.Host = host;
        if (auth) req.Headers.Add("X-CSRF-Token", f.Token);
        foreach (var (k, v) in headers ?? []) req.Headers.TryAddWithoutValidation(k, v);
        if (body is not null)
        {
            var bytes = body is byte[] b ? b : body is string s ? Encoding.UTF8.GetBytes(s) : Encoding.UTF8.GetBytes(System.Text.Json.JsonSerializer.Serialize(body));
            req.Content = new ByteArrayContent(bytes);
            req.Content.Headers.ContentType = MediaTypeHeaderValue.Parse(contentType);
        }
        var resp = await c.SendAsync(req);
        return (resp.StatusCode, resp, await resp.Content.ReadAsByteArrayAsync());
    }

    private static JsonObject J(byte[] b) => JsonNode.Parse(b)!.AsObject();

    [Fact]
    public async Task IndexHasCspAndToken()
    {
        var (st, resp, body) = await Req(HttpMethod.Get, "/", auth: false);
        Assert.Equal(HttpStatusCode.OK, st);
        Assert.Contains("script-src 'self'", resp.Headers.GetValues("Content-Security-Policy").First());
        Assert.Equal("nosniff", resp.Headers.GetValues("X-Content-Type-Options").First());
        var html = Encoding.UTF8.GetString(body);
        Assert.Contains(f.Token, html);
        Assert.DoesNotContain("{{CSRF_TOKEN}}", html);
    }

    [Fact]
    public async Task ApiRequiresCsrf()
    {
        Assert.Equal(HttpStatusCode.Forbidden, (await Req(HttpMethod.Get, "/api/status", auth: false)).Status);
        Assert.Equal(HttpStatusCode.Forbidden, (await Req(HttpMethod.Post, "/api/trace", new { identifier = "W07632100028" }, auth: false)).Status);
        Assert.Equal(HttpStatusCode.Forbidden, (await Req(HttpMethod.Get, "/api/status", auth: false, headers: new() { ["X-CSRF-Token"] = "wrong" })).Status);
    }

    [Fact]
    public async Task ForeignOriginRejected() =>
        Assert.Equal(HttpStatusCode.Forbidden, (await Req(HttpMethod.Post, "/api/trace", new { identifier = "X" }, headers: new() { ["Origin"] = "http://evil.example" })).Status);

    [Fact]
    public async Task DnsRebindingHostRejected() =>
        Assert.Equal(HttpStatusCode.Forbidden, (await Req(HttpMethod.Get, "/", auth: false, host: "evil.example")).Status);

    [Fact]
    public async Task StatusAndTrace()
    {
        var (st, _, body) = await Req(HttpMethod.Get, "/api/status");
        Assert.Equal(HttpStatusCode.OK, st);
        Assert.True(J(body)["is_demo"]!.GetValue<bool>());
        (st, _, body) = await Req(HttpMethod.Post, "/api/trace", new { identifier = "W07632100028" });
        Assert.Equal(HttpStatusCode.OK, st);
        Assert.Equal(1, J(body)["summary"]!["unique_defects"]!.GetValue<int>());
    }

    [Fact]
    public async Task BadInput400()
    {
        var (st, _, body) = await Req(HttpMethod.Post, "/api/trace", new { identifier = "A'B" });
        Assert.Equal(HttpStatusCode.BadRequest, st);
        Assert.NotNull(J(body)["error"]);
        Assert.Equal(HttpStatusCode.BadRequest, (await Req(HttpMethod.Post, "/api/trace", "not json")).Status);
        Assert.Equal(HttpStatusCode.UnsupportedMediaType, (await Req(HttpMethod.Post, "/api/trace", "{}", contentType: "text/plain")).Status);
    }

    [Fact]
    public async Task BodyLimit() =>
        Assert.Equal(HttpStatusCode.RequestEntityTooLarge, (await Req(HttpMethod.Post, "/api/trace", "{" + new string(' ', 70000) + "}")).Status);

    [Fact]
    public async Task ReportDownload()
    {
        var (st, resp, body) = await Req(HttpMethod.Post, "/api/report", new { identifier = "W07632100028", format = "xlsx" });
        Assert.Equal(HttpStatusCode.OK, st);
        Assert.Contains("attachment", resp.Content.Headers.ContentDisposition!.ToString());
        Assert.Equal((byte)'P', body[0]);
        Assert.Equal((byte)'K', body[1]);
    }

    [Fact]
    public async Task StaticAndTraversal()
    {
        var (st, resp, _) = await Req(HttpMethod.Get, "/static/js/app.js", auth: false);
        Assert.Equal(HttpStatusCode.OK, st);
        Assert.Contains("javascript", resp.Content.Headers.ContentType!.ToString());
        foreach (var p in new[] { "/static/../Program.cs", "/static/%2e%2e/config.example.json", "/static/../../etc/passwd", "/static/..%2fconfig.example.json" })
            Assert.Equal(HttpStatusCode.NotFound, (await Req(HttpMethod.Get, p, auth: false)).Status);
    }

    [Fact]
    public async Task ConfigCannotEnableSecurityFlags() =>
        Assert.Equal(HttpStatusCode.BadRequest, (await Req(HttpMethod.Post, "/api/config", new { values = new Dictionary<string, object> { ["security.live_mode_approved"] = true } })).Status);

    [Fact]
    public async Task Diagnostics()
    {
        var (st, _, body) = await Req(HttpMethod.Post, "/api/diagnostics/test", new { entity = "$metadata" });
        Assert.Equal(HttpStatusCode.OK, st);
        Assert.Equal("4", J(body)["odata_version"]!.GetValue<string>());
        (st, _, body) = await Req(HttpMethod.Get, "/api/diagnostics/text");
        var txt = J(body)["text"]!.GetValue<string>();
        Assert.Contains("Diagnóstico OData", txt);
        Assert.DoesNotContain("password", txt, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(HttpStatusCode.BadRequest, (await Req(HttpMethod.Post, "/api/diagnostics/test", new { entity = "ProductivityOverTime" })).Status);
    }
}

/// <summary>Interacciones esenciales del frontend verificadas estáticamente.</summary>
public class FrontendStaticTests
{
    private static readonly string Root = Path.Combine(AppContext.BaseDirectory, "wwwroot");
    private static readonly string Html = File.ReadAllText(Path.Combine(Root, "index.html"));
    private static readonly string Js = File.ReadAllText(Path.Combine(Root, "js", "app.js")) + File.ReadAllText(Path.Combine(Root, "js", "ui.js"));

    [Fact]
    public void NoUnsafeDomSinks()
    {
        foreach (var sink in new[] { "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function" })
            Assert.DoesNotContain(sink, Js);
    }

    [Fact]
    public void NoInlineScriptsOrHandlers()
    {
        Assert.DoesNotMatch(new Regex("<script(?![^>]*\\bsrc=)[^>]*>"), Html);
        Assert.DoesNotMatch(new Regex("\\son[a-z]+=\""), Html);
        Assert.DoesNotContain("style=\"", Html);
    }

    [Fact]
    public void AllReferencedIdsExist()
    {
        var ids = Regex.Matches(Html, "id=\"([^\"]+)\"").Select(m => m.Groups[1].Value).ToHashSet();
        var used = Regex.Matches(Js, "\\$\\(\"([^\"]+)\"\\)").Concat(Regex.Matches(Js, "getElementById\\(\"([^\"]+)\"\\)")).Select(m => m.Groups[1].Value).ToHashSet();
        Assert.Empty(used.Except(ids));
    }

    [Fact]
    public void SidebarHasNineSections()
    {
        var views = Regex.Matches(Html, "data-view=\"([a-z]+)\"").Select(m => m.Groups[1].Value).ToList();
        Assert.Equal(["dashboard", "trace", "pulse", "quality", "rework", "history", "reports", "config", "diagnostics"], views);
        foreach (var v in views) Assert.Contains($"id=\"view-{v}\"", Html);
    }

    [Fact]
    public void ApiRoutesUsedExist()
    {
        var known = new HashSet<string> { "/api/status", "/api/history", "/api/config", "/api/diagnostics", "/api/diagnostics/text", "/api/trace",
            "/api/pulse", "/api/quality", "/api/quality/close-times", "/api/rework", "/api/history/clear", "/api/config/reset",
            "/api/diagnostics/test", "/api/logs/open", "/api/report" };
        var used = Regex.Matches(Js, "api\\(\"(/api/[^\"]+)\"").Select(m => m.Groups[1].Value).ToHashSet();
        Assert.Empty(used.Except(known));
    }

    [Fact]
    public void NoPassLabelInUi() => Assert.DoesNotMatch(new Regex("[\"'>]PASS[\"'<]"), Js + Html);
}
