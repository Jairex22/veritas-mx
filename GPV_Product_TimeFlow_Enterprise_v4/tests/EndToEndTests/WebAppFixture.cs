using System.Net;
using System.Net.Sockets;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Playwright;

namespace GPV.ProductTimeFlow.EndToEndTests;

/// <summary>
/// Inicia la aplicación Web real (Kestrel, puerto libre) con datos DEMO sintéticos en una carpeta temporal y un
/// navegador Chromium. Navegador: PLAYWRIGHT_BROWSERS_PATH o el instalado con "pwsh bin/Debug/net10.0/playwright.ps1 install chromium".
/// </summary>
public sealed class WebAppFixture : IAsyncLifetime
{
    public const string Password = "Demo#TimeFlow2026";
    private readonly string _dataRoot = Path.Combine(Path.GetTempPath(), $"tf-e2e-{Guid.NewGuid():N}");
    private WebApplicationFactory<Program>? _factory;
    public IPlaywright Playwright { get; private set; } = default!;
    public IBrowser Browser { get; private set; } = default!;
    public string BaseUrl { get; private set; } = "";
    public string ScreenshotDir { get; } = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../docs/screenshots"));

    public async Task InitializeAsync()
    {
        BaseUrl = "http://localhost";
        _factory = new WebApplicationFactory<Program>().WithWebHostBuilder(b =>
        {
            b.UseEnvironment("Development");
            b.UseSetting("TimeFlow:DataRoot", _dataRoot);
            b.UseSetting("TimeFlow:PublicBaseUrl", BaseUrl);
            b.UseSetting("Demo:SyntheticEmployees", "24");
            b.UseSetting("Demo:SeedSampleRequests", "true");
            b.UseSetting("Email:PollSeconds", "2");
            b.UseSetting("urls", "http://127.0.0.1:0");
        });
        _factory.UseKestrel();
        _factory.StartServer();
        var server = _factory.Services.GetRequiredService<Microsoft.AspNetCore.Hosting.Server.IServer>();
        var addresses = server.Features.Get<Microsoft.AspNetCore.Hosting.Server.Features.IServerAddressesFeature>()?.Addresses;
        var first = addresses?.FirstOrDefault(a => a.StartsWith("http://"));
        if (first is not null) BaseUrl = first.Replace("127.0.0.1", "localhost").Replace("[::]", "localhost").TrimEnd('/');
        Console.WriteLine("E2E server: " + string.Join(", ", addresses ?? []) + " → " + BaseUrl);

        Playwright = await Microsoft.Playwright.Playwright.CreateAsync();
        var options = new BrowserTypeLaunchOptions { Headless = true };
        var custom = Environment.GetEnvironmentVariable("TIMEFLOW_CHROMIUM_PATH");
        if (!string.IsNullOrEmpty(custom)) options.ExecutablePath = custom;
        Browser = await Playwright.Chromium.LaunchAsync(options);
        Directory.CreateDirectory(ScreenshotDir);
    }

    public async Task<IPage> LoginAsync(string email, int width = 1440, int height = 900)
    {
        var context = await Browser.NewContextAsync(new BrowserNewContextOptions { ViewportSize = new ViewportSize { Width = width, Height = height }, AcceptDownloads = true, Locale = "es-MX", TimezoneId = "America/Mexico_City" });
        context.SetDefaultTimeout(20_000);
        var page = await context.NewPageAsync();
        await page.GotoAsync(BaseUrl + "/account/login");
        await page.FillAsync("[data-testid=login-email]", email);
        await page.FillAsync("[data-testid=login-password]", Password);
        await page.ClickAsync("[data-testid=login-submit]");
        await page.WaitForURLAsync(u => !u.Contains("/account/login"));
        await WaitInteractiveAsync(page);
        return page;
    }

    /// <summary>Espera a que el circuito de Blazor Server esté activo (los botones responden).</summary>
    public static async Task WaitInteractiveAsync(IPage page)
    {
        await page.WaitForSelectorAsync("main.content");
        await page.WaitForFunctionAsync("() => window.Blazor && document.querySelector('.user-meta strong') && document.querySelector('.user-meta strong').textContent !== '…'");
        await page.WaitForTimeoutAsync(300);
    }

    public async Task GotoAsync(IPage page, string path)
    {
        await page.GotoAsync(BaseUrl + path);
        await WaitInteractiveAsync(page);
    }

    public static async Task DrawSignatureAsync(IPage page, string canvasId)
    {
        await page.WaitForSelectorAsync($"#{canvasId}");
        var ok = await page.EvaluateAsync<bool>($"async () => (await import('/js/app.js')).drawTestSignature('#{canvasId}')");
        Assert.True(ok, "No se pudo dibujar la firma de prueba.");
        await page.WaitForTimeoutAsync(300);
    }

    public async Task ScreenshotAsync(IPage page, string name, bool fullPage = false) =>
        await page.ScreenshotAsync(new PageScreenshotOptions { Path = Path.Combine(ScreenshotDir, name + ".png"), FullPage = fullPage });

    public async Task DisposeAsync()
    {
        await Browser.DisposeAsync();
        Playwright.Dispose();
        _factory?.Dispose();
        try { Directory.Delete(_dataRoot, true); } catch { /* best effort */ }
    }

    private static int FreePort()
    {
        var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        var port = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        return port;
    }
}

[CollectionDefinition("web")]
public sealed class WebCollection : ICollectionFixture<WebAppFixture>;
