namespace GPV.ProductTimeFlow.EndToEndTests;

/// <summary>Capturas reales en las resoluciones objetivo y verificación de que no hay desbordamiento horizontal.</summary>
[Collection("web")]
public sealed class VisualTests(WebAppFixture app)
{
    public static TheoryData<string, int, int> Viewports => new()
    {
        { "desktop-1920x1080", 1920, 1080 }, { "laptop-1366x768", 1366, 768 }, { "tablet-768x1024", 768, 1024 },
        { "mobile-390x844", 390, 844 }, { "mobile-360x800", 360, 800 },
    };

    [Theory, MemberData(nameof(Viewports))]
    public async Task Pantallas_principales_sin_desbordamiento(string name, int width, int height)
    {
        var page = await app.LoginAsync("laura.jefa@demo.timeflow.example", width, height);
        foreach (var (slug, path) in new[] { ("inicio", "/"), ("nueva", "/solicitudes/nueva/Vacation"), ("calendario", "/calendario"), ("aprobaciones", "/aprobaciones") })
        {
            await app.GotoAsync(page, path);
            await page.WaitForTimeoutAsync(400);
            var overflow = await page.EvaluateAsync<int>("() => document.documentElement.scrollWidth - document.documentElement.clientWidth");
            Assert.True(overflow <= 1, $"{name} {path}: desbordamiento horizontal de {overflow}px");
            await app.ScreenshotAsync(page, $"{name}-{slug}");
        }
        await page.Context.CloseAsync();
    }

    [Fact]
    public async Task Login_y_tema_oscuro()
    {
        var ctx = await app.Browser.NewContextAsync(new() { ViewportSize = new() { Width = 1440, Height = 900 } });
        var page = await ctx.NewPageAsync();
        await page.GotoAsync(app.BaseUrl + "/account/login");
        Assert.Contains("Bienvenido a GPV Product TimeFlow", await page.InnerTextAsync("body"));
        await app.ScreenshotAsync(page, "desktop-login");
        await ctx.CloseAsync();

        var admin = await app.LoginAsync("admin.producto@demo.timeflow.example");
        await admin.EvaluateAsync("() => { localStorage.setItem('tf-theme','dark'); }");
        await app.GotoAsync(admin, "/admin/empleados");
        await app.ScreenshotAsync(admin, "desktop-admin-empleados-oscuro");
        await app.GotoAsync(admin, "/admin/auditoria");
        await admin.ClickAsync("[data-testid=verify-audit]");
        await admin.WaitForSelectorAsync("text=Cadena íntegra");
        await app.ScreenshotAsync(admin, "desktop-auditoria-oscuro");
        await admin.Context.CloseAsync();
    }
}
