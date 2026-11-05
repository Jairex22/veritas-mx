using System.IO.Compression;
using System.Text;
using System.Text.Json.Nodes;
using System.Xml.Linq;
using Gpv.Sqi.Config;
using Gpv.Sqi.Data;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Reports;
using Xunit;

namespace Gpv.Sqi.Tests;

public class CacheTests
{
    private readonly CacheRepository _repo = new(new Database(TestHelpers.TempDb()));

    [Fact]
    public void EmptyGuidNotUsedAsKey()
    {
        var smt = TestHelpers.Smt;
        Assert.StartsWith("hash:", CacheRepository.DedupKey("SMT", smt[0]));
        Assert.NotEqual(CacheRepository.DedupKey("SMT", smt[0]), CacheRepository.DedupKey("SMT", smt[1]));
        var real = smt[0].Clone(); real["ODataKey"] = "1b4e28ba-2fa1-11d2-883f-0016d3cca427";
        Assert.Equal("key:1b4e28ba-2fa1-11d2-883f-0016d3cca427", CacheRepository.DedupKey("SMT", real));
    }

    [Fact]
    public void DedupBetweenWindows()
    {
        _repo.Store("SMT", TestHelpers.Smt, "demo");
        _repo.Store("SMT", TestHelpers.Smt, "demo");
        Assert.Equal(4L, _repo.Counts()["CachedSMTEvents"]);
    }

    [Fact]
    public void HistorySameDefectNotOverwritten()
    {
        _repo.Store("QualityHistory", TestHelpers.History, "live");
        Assert.Equal(3, _repo.HistoryByDefects([TestHelpers.History[0].Str("DefectID")!], "live").Rows.Count);
    }

    [Fact]
    public void DemoAndLiveNeverMixed()
    {
        _repo.Store("SMT", TestHelpers.Smt, "demo");
        Assert.Empty(_repo.SmtByIdentifier("W07632100028", "live").Rows);
        Assert.Equal(4, _repo.SmtByIdentifier("W07632100028", "demo").Rows.Count);
        Assert.Equal(0, _repo.Store("SMT", TestHelpers.Smt, "cache"));
    }

    [Fact]
    public void WindowQueryUsesUtc()
    {
        _repo.Store("SMT", TestHelpers.Smt, "live");
        var start = new DateTimeOffset(2026, 11, 4, 21, 20, 0, TimeSpan.Zero);   // 15:20 -06:00
        var (rows, _) = _repo.SmtInWindow(start, start.AddHours(1), "live", 100);
        Assert.Equal(3, rows.Count);
    }
}

public class ConfigTests
{
    [Fact]
    public void PasswordInConfigRejected()
    {
        var p = Path.Combine(Path.GetTempPath(), $"cfg_{Guid.NewGuid():N}.json");
        File.WriteAllText(p, "{\"odata\": {\"password\": \"123456\"}}");
        try { Assert.Throws<ConfigException>(() => AppConfig.Load(p)); }
        finally { File.Delete(p); }
    }

    [Fact]
    public void ExampleConfigLoads()
    {
        var cfg = AppConfig.Load(Path.Combine(AppContext.BaseDirectory, "config.example.json"));
        Assert.Equal("demo", cfg.Mode);
        Assert.False(cfg.Bool("security.live_mode_approved"));
    }

    [Theory]
    [InlineData("security.live_mode_approved")]
    [InlineData("security.allow_basic_auth_over_http")]
    [InlineData("odata.password")]
    public void SecurityFlagsNotEditable(string key) =>
        Assert.Throws<ConfigException>(() => AppConfig.ValidateSetting(key, JsonValue.Create(true)));

    [Fact]
    public void Limits()
    {
        Assert.Throws<ConfigException>(() => AppConfig.ValidateSetting("odata.max_retries", JsonValue.Create(20)));
        Assert.Throws<ConfigException>(() => AppConfig.ValidateSetting("pulse.refresh_interval_seconds", JsonValue.Create(10)));
        Assert.Throws<ConfigException>(() => AppConfig.ValidateSetting("odata.base_url", JsonValue.Create("http://u:p@host/odata")));
        Assert.Equal("http://h:1/odata/", AppConfig.ValidateSetting("odata.base_url", JsonValue.Create("http://h:1/odata"))!.GetValue<string>());
    }

    [Fact]
    public void OverridesApplyAndInvalidIgnored()
    {
        var cfg = AppConfig.Defaults().WithOverrides(new Dictionary<string, JsonNode?>
        {
            ["mode"] = JsonValue.Create("live"), ["odata.max_retries"] = JsonValue.Create(99), ["security.live_mode_approved"] = JsonValue.Create(true),
        });
        Assert.Equal("live", cfg.Mode);
        Assert.Equal(0, cfg.Int("odata.max_retries"));   // 99 inválido: se conserva el valor por defecto
        Assert.False(cfg.Bool("security.live_mode_approved"));
    }
}

public class LogSanitizeTests
{
    [Fact]
    public void Sanitize()
    {
        var s = AppLog.Sanitize("Authorization: Basic NDIxNzg6MTIzNDU2 password=123456 http://u:p@h/x");
        Assert.DoesNotContain("NDIxNzg6MTIzNDU2", s);
        Assert.DoesNotContain("123456", s);
        Assert.DoesNotContain("u:p@", s);
    }
}

public class ReportTests
{
    private static UnitReport Sample(bool demo = true) => new("Reporte de unidad X", "X", demo,
        "El cierre de un defecto no constituye por sí mismo evidencia de aprobación final de la unidad.",
        [
            new("General", [new() { "Cliente", "=HYPERLINK(\"http://evil\")" }, new() { "Identifier", "<script>x</script>" }]),
            new("Eventos de proceso", [new() { "Fecha", "Operación" }, new() { "2026-11-04", "SMT REPAIR" }, new() { "n", 5 }]),
        ]);

    [Fact]
    public void Csv()
    {
        var data = Encoding.UTF8.GetString(Exporters.ToCsv(Sample())).TrimStart('\uFEFF');
        Assert.Contains("DEMOSTRACIÓN", data);
        Assert.Contains("El cierre de un defecto", data);
        Assert.Contains("'=HYPERLINK", data);   // inyección de fórmulas neutralizada
    }

    [Fact]
    public void XlsxIsValidOoxml()
    {
        using var zip = new ZipArchive(new MemoryStream(Exporters.ToXlsx(Sample())));
        var names = zip.Entries.Select(e => e.FullName).ToList();
        foreach (var required in new[] { "[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml", "xl/styles.xml" })
            Assert.Contains(required, names);
        foreach (var e in zip.Entries)
        {
            using var s = e.Open();
            XDocument.Load(s);   // XML bien formado
        }
        using var sr = new StreamReader(zip.GetEntry("xl/worksheets/sheet1.xml")!.Open());
        var sheet = sr.ReadToEnd();
        Assert.Contains("&lt;script&gt;", sheet);
        Assert.Contains("&#39;=HYPERLINK", sheet);
    }

    [Fact]
    public void HtmlEscapes()
    {
        var h = Encoding.UTF8.GetString(Exporters.ToHtml(Sample()));
        Assert.DoesNotContain("<script>x</script>", h);
        Assert.Contains("&lt;script&gt;", h);
        Assert.Contains("DEMOSTRACI", h);
        Assert.DoesNotContain("DATOS DE DEMOSTRACI", Encoding.UTF8.GetString(Exporters.ToHtml(Sample(false))));
    }
}

public class ConfigNumericTests
{
    [Fact]
    public void NumReadsInMemoryAndParsedValues()
    {
        var cfg = AppConfig.Defaults();
        cfg.Set("odata.timeout_seconds", 7);          // int en memoria
        cfg.Set("odata.backoff_seconds", 1.5);        // double en memoria
        Assert.Equal(7, cfg.Num("odata.timeout_seconds"));
        Assert.Equal(1.5, cfg.Num("odata.backoff_seconds"));
        var withUi = cfg.WithOverrides(new Dictionary<string, JsonNode?> { ["odata.max_retries"] = JsonValue.Create(2) });
        Assert.Equal(2, withUi.Int("odata.max_retries"));   // regresión: valor guardado desde la pantalla Configuración
    }
}
