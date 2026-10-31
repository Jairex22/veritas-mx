using System.Text.RegularExpressions;
using ClosedXML.Excel;
using Microsoft.Playwright;

namespace GPV.ProductTimeFlow.EndToEndTests;

[Collection("web")]
public sealed class ApprovalFlowTests(WebAppFixture app)
{
    private const string Ana = "ana.empleada@demo.timeflow.example";
    private const string Laura = "laura.jefa@demo.timeflow.example";
    private const string Carlos = "carlos.superior@demo.timeflow.example";
    private const string Sofia = "registro.admin@demo.timeflow.example";

    private static DateOnly PastWorkday(int daysBack)
    {
        var tz = TimeZoneInfo.FindSystemTimeZoneById("America/Mexico_City");
        var d = DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, tz)).AddDays(-daysBack);
        while (d.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday) d = d.AddDays(-1);
        return d;
    }

    /// <summary>Empleado crea tiempo extra por el asistente y la envía; devuelve la URL del expediente.</summary>
    private async Task<string> CreateOvertimeAsync(IPage page, DateOnly date, string start, string end, string? screenshotPrefix = null)
    {
        await app.GotoAsync(page, "/solicitudes/nueva");
        if (screenshotPrefix is not null) await app.ScreenshotAsync(page, screenshotPrefix + "-01-tipo");
        await page.ClickAsync("[data-testid=type-Overtime]");
        await page.FillAsync("[data-testid=ot-date]", date.ToString("yyyy-MM-dd"));
        await page.FillAsync("[data-testid=ot-start]", start);
        await page.FillAsync("[data-testid=ot-end]", end);
        await page.FillAsync("[data-testid=ot-project]", "Plataforma de configuración");
        await page.FillAsync("[data-testid=reason]", "Liberación nocturna del módulo");
        await page.FillAsync("[data-testid=ot-activity]", "Monitoreo del despliegue y pruebas de humo posteriores.");
        await page.Locator("[data-testid=ot-activity]").BlurAsync();
        await page.WaitForTimeoutAsync(500);
        if (screenshotPrefix is not null) await app.ScreenshotAsync(page, screenshotPrefix + "-02-datos", true);
        await page.ClickAsync("[data-testid=save-draft]");
        await page.WaitForSelectorAsync("[data-testid=to-review]");
        await page.ClickAsync("[data-testid=to-review]");
        await page.WaitForSelectorAsync("[data-testid=submit-request]");
        if (screenshotPrefix is not null) await app.ScreenshotAsync(page, screenshotPrefix + "-03-revision", true);
        await page.ClickAsync("[data-testid=submit-request]");
        await page.WaitForURLAsync(new Regex(@"/solicitudes/[0-9a-f\-]{36}$"));
        await page.WaitForSelectorAsync("[data-testid=folio]");
        return new Uri(page.Url).AbsolutePath;
    }

    private async Task DecideAsync(string email, string requestPath, string action, string? comment = null, string? screenshot = null)
    {
        var page = await app.LoginAsync(email);
        await app.GotoAsync(page, requestPath);
        await page.ClickAsync($"[data-testid={action}]");
        if (action == "approve")
        {
            await WebAppFixture.DrawSignatureAsync(page, "approver-signature");
            await page.CheckAsync("[data-testid=consent]");
        }
        else await page.FillAsync("[data-testid=decision-comment]", comment ?? "Favor de corregir la información capturada.");
        if (screenshot is not null) await app.ScreenshotAsync(page, screenshot);
        await page.ClickAsync("[data-testid=confirm-decision]");
        await page.WaitForSelectorAsync(".modal", new() { State = WaitForSelectorState.Detached });
        await page.Context.CloseAsync();
    }

    private static async Task<string> StatusAsync(IPage page) => (await page.Locator("header .chip").First.InnerTextAsync()).Trim();

    [Fact]
    public async Task Flujo_completo_tres_filtros_con_firmas_pdf_excel_y_registro()
    {
        // 1-3. Empleado inicia sesión, crea y envía.
        var ana = await app.LoginAsync(Ana);
        Assert.Contains("Hola, Ana", await ana.InnerTextAsync("[data-testid=greeting]"));
        await app.ScreenshotAsync(ana, "desktop-dashboard-empleado");
        var path = await CreateOvertimeAsync(ana, PastWorkday(3), "22:00", "01:30", "wizard");
        Assert.Equal("Pendiente de jefa directa", await StatusAsync(ana));
        Assert.Contains("3.5 horas", await ana.InnerTextAsync("main"));
        await ana.Context.CloseAsync();

        // 4-6. Jefa revisa, firma y aprueba.
        await DecideAsync(Laura, path, "approve", screenshot: "firma-jefa-directa");
        // 7-8. Jefe superior firma y aprueba.
        await DecideAsync(Carlos, path, "approve");

        // 9-12. Registro administrativo: recibe, descarga Excel y PDF, registra y procesa.
        var sofia = await app.LoginAsync(Sofia);
        await app.GotoAsync(sofia, "/registro");
        await app.ScreenshotAsync(sofia, "desktop-registro-administrativo");
        await app.GotoAsync(sofia, path);
        Assert.Equal("Pendiente de registro administrativo", await StatusAsync(sofia));
        var folio = (await sofia.InnerTextAsync("[data-testid=folio]")).Trim();

        var excel = await sofia.APIRequest.GetAsync(app.BaseUrl + "/files/exports/requests.xlsx?set=approved");
        Assert.Equal(200, excel.Status);
        using (var wb = new XLWorkbook(new MemoryStream(await excel.BodyAsync())))
        {
            Assert.Contains(wb.Worksheet("Detalle").CellsUsed(), c => c.GetString() == folio);
            Assert.True(wb.Worksheets.Contains("Resumen") && wb.Worksheets.Contains("Metadatos"));
        }
        var pdf = await sofia.APIRequest.GetAsync(app.BaseUrl + path.Replace("/solicitudes/", "/files/requests/") + "/pdf?download=true");
        Assert.Equal(200, pdf.Status);
        var pdfBytes = await pdf.BodyAsync();
        Assert.StartsWith("%PDF", System.Text.Encoding.ASCII.GetString(pdfBytes, 0, 4));
        File.WriteAllBytes(Path.Combine(app.ScreenshotDir, "ejemplo-expediente.pdf"), pdfBytes);

        await sofia.ClickAsync("[data-testid=admin-receive]");
        await sofia.WaitForSelectorAsync("text=Marcada como recibida");
        await sofia.ClickAsync("[data-testid=admin-register]");
        await sofia.FillAsync("[data-testid=admin-comment]", "Capturado en sistema administrativo.");
        await sofia.ClickAsync("[data-testid=confirm-admin]");
        await sofia.WaitForSelectorAsync("[data-testid=admin-complete]");
        Assert.Equal("Registrada administrativamente", await StatusAsync(sofia));
        await sofia.ClickAsync("[data-testid=admin-complete]");
        await sofia.ClickAsync("[data-testid=confirm-admin]");
        await sofia.WaitForSelectorAsync("[data-testid=admin-complete]", new() { State = WaitForSelectorState.Detached });
        await sofia.Context.CloseAsync();

        // 13. Empleado consulta el resultado.
        ana = await app.LoginAsync(Ana);
        await app.GotoAsync(ana, path);
        Assert.Equal("Completada", await StatusAsync(ana));
        Assert.Equal(2, await ana.Locator(".sig-card:not(.invalid)").CountAsync());
        await app.ScreenshotAsync(ana, "desktop-expediente-completado", true);
        await ana.Context.CloseAsync();
    }

    [Fact]
    public async Task Rechazo_por_jefa_detiene_la_solicitud()
    {
        var ana = await app.LoginAsync(Ana);
        var path = await CreateOvertimeAsync(ana, PastWorkday(5), "05:00", "06:00");
        await ana.Context.CloseAsync();
        await DecideAsync(Laura, path, "reject", "No corresponde a actividades planeadas del sprint.");
        var carlos = await app.LoginAsync(Carlos);
        await app.GotoAsync(carlos, path);
        Assert.Equal("Rechazada por jefa directa", await StatusAsync(carlos));
        Assert.Equal(0, await carlos.Locator("[data-testid=approve]").CountAsync());
        await carlos.Context.CloseAsync();
    }

    [Fact]
    public async Task Devolucion_correccion_y_reenvio()
    {
        var ana = await app.LoginAsync(Ana);
        var path = await CreateOvertimeAsync(ana, PastWorkday(7), "06:00", "07:30");
        await ana.Context.CloseAsync();
        await DecideAsync(Laura, path, "return", "Indica el proyecto exacto, por favor.");

        ana = await app.LoginAsync(Ana);
        await app.GotoAsync(ana, path);
        Assert.Equal("Devuelta para corrección", await StatusAsync(ana));
        Assert.Contains("Indica el proyecto exacto", await ana.InnerTextAsync("main"));
        await ana.ClickAsync("[data-testid=edit-request]");
        await ana.WaitForSelectorAsync("[data-testid=ot-project]");
        await ana.FillAsync("[data-testid=ot-project]", "Portal de documentación técnica v2");
        await ana.ClickAsync("[data-testid=save-draft]");
        await ana.ClickAsync("[data-testid=to-review]");
        await ana.ClickAsync("[data-testid=submit-request]");
        await ana.WaitForURLAsync(new Regex(@"/solicitudes/[0-9a-f\-]{36}$"));
        await ana.WaitForSelectorAsync("[data-testid=folio]");
        Assert.Equal("Pendiente de jefa directa", await StatusAsync(ana));
        await ana.Context.CloseAsync();
    }

    [Fact]
    public async Task Cancelacion_por_el_empleado()
    {
        var ana = await app.LoginAsync(Ana);
        var path = await CreateOvertimeAsync(ana, PastWorkday(9), "07:00", "08:00");
        await ana.ClickAsync("[data-testid=cancel-request]");
        await ana.ClickAsync("[data-testid=confirm-cancel]");
        await ana.WaitForSelectorAsync("[data-testid=cancel-request]", new() { State = WaitForSelectorState.Detached });
        Assert.Equal("Cancelada", await StatusAsync(ana));
        await ana.Context.CloseAsync();

        var laura = await app.LoginAsync(Laura);
        await app.GotoAsync(laura, path);
        Assert.Equal(0, await laura.Locator("[data-testid=approve]").CountAsync());
        await laura.Context.CloseAsync();
    }

    [Fact]
    public async Task Empleado_no_puede_ver_expediente_ajeno()
    {
        var ana = await app.LoginAsync(Ana);
        var path = await CreateOvertimeAsync(ana, PastWorkday(11), "04:00", "05:00");
        await ana.Context.CloseAsync();
        var sofia = await app.LoginAsync(Sofia); // registro aún no tiene acceso: falta autorización gerencial
        await app.GotoAsync(sofia, path);
        Assert.Contains("Expediente no disponible", await sofia.InnerTextAsync("main"));
        await sofia.Context.CloseAsync();
    }
}
