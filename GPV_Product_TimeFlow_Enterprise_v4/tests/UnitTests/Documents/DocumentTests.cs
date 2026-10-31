using ClosedXML.Excel;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Infrastructure;
using GPV.ProductTimeFlow.Infrastructure.Documents;
using GPV.ProductTimeFlow.Infrastructure.Seeding;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.UnitTests.Documents;

public class SyntheticSignatureTests
{
    private static readonly byte[] PngMagic = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];

    [Fact]
    public void Create_produces_png_with_magic_bytes_and_ihdr()
    {
        var png = SyntheticSignature.Create(1);
        Assert.True(png.Length > 200);
        Assert.Equal(PngMagic, png[..8]);
        Assert.Equal("IHDR", System.Text.Encoding.ASCII.GetString(png, 12, 4));
        // ancho/alto big-endian
        Assert.Equal(360, (png[16] << 24) | (png[17] << 16) | (png[18] << 8) | png[19]);
        Assert.Equal(120, (png[20] << 24) | (png[21] << 16) | (png[22] << 8) | png[23]);
        Assert.Equal("IEND", System.Text.Encoding.ASCII.GetString(png, png.Length - 8, 4));
        Assert.True(FileSignatures.Matches(".png", png));
    }

    [Fact]
    public void Same_seed_is_deterministic_and_different_seeds_differ()
    {
        Assert.Equal(SyntheticSignature.Create(7), SyntheticSignature.Create(7));
        Assert.NotEqual(SyntheticSignature.Create(7), SyntheticSignature.Create(8));
        Assert.Equal(SyntheticSignature.Create(3), Convert.FromBase64String(SyntheticSignature.Base64(3)));
    }

    [Fact]
    public void Synthetic_signature_is_accepted_by_signature_decoder()
    {
        var decoded = WorkflowService.DecodeSignature("data:image/png;base64," + SyntheticSignature.Base64(2));
        Assert.Equal(SyntheticSignature.Create(2), decoded);
    }
}

public class ExcelExporterTests
{
    private const string Injection = "=HYPERLINK(\"http://x\")";

    private static ExportRow Row(string reason, string? observations = null) => new(
        "TF-2026-000001", new DateTime(2026, 3, 10, 9, 0, 0), "P-0100", "Ana Torres Lozano", "Producto", "Ingeniería", "Tiempo extra",
        new DateOnly(2026, 3, 10), new DateOnly(2026, 3, 10), 2.5m, 0m, reason,
        "Laura Hernández Vega", new DateTime(2026, 3, 10, 10, 0, 0), "Carlos Mendoza Ríos", new DateTime(2026, 3, 10, 11, 0, 0),
        "Completada", new DateTime(2026, 3, 11, 9, 0, 0), observations, Guid.Parse("11111111-2222-3333-4444-555555555555"));

    private static XLWorkbook Export(params ExportRow[] rows)
    {
        var bytes = new ExcelExporter().ExportRequests(rows, new ExportMetadata("Sofía Ramírez Castro", new DateTime(2026, 3, 12, 8, 0, 0),
            "{\"Set\":\"approved\"}", "DEMO · datos sintéticos", "America/Mexico_City"));
        Assert.Equal((byte)'P', bytes[0]);
        Assert.Equal((byte)'K', bytes[1]);
        return new XLWorkbook(new MemoryStream(bytes));
    }

    [Fact]
    public void SetSafeText_neutralizes_formula_prefixes()
    {
        using var wb = new XLWorkbook();
        var ws = wb.AddWorksheet("T");
        string[] dangerous = [Injection, "+1+1", "-2+3", "@SUM(A1)", "\tcmd", "\rcmd"];
        for (var i = 0; i < dangerous.Length; i++)
        {
            var cell = ws.Cell(i + 1, 1);
            ExcelExporter.SetSafeText(cell, dangerous[i]);
            Assert.False(cell.HasFormula);
            Assert.True(cell.Style.IncludeQuotePrefix);
            Assert.Equal(dangerous[i], cell.GetString());
        }
        var safe = ws.Cell(10, 1);
        ExcelExporter.SetSafeText(safe, "Texto normal");
        Assert.False(safe.Style.IncludeQuotePrefix);
        ExcelExporter.SetSafeText(ws.Cell(11, 1), null);
        Assert.Equal("", ws.Cell(11, 1).GetString());
    }

    [Fact]
    public void Exported_reason_with_formula_is_stored_as_text_not_formula()
    {
        using var wb = Export(Row(Injection, "@cmd|' /C calc'!A0"));
        var detail = wb.Worksheet("Detalle");
        var reasonCell = detail.Cell(2, 12);
        Assert.False(reasonCell.HasFormula);
        Assert.Equal(string.Empty, reasonCell.FormulaA1);
        Assert.Equal(Injection, reasonCell.GetString());
        Assert.True(reasonCell.Style.IncludeQuotePrefix);

        var obsCell = detail.Cell(2, 19);
        Assert.False(obsCell.HasFormula);
        Assert.Equal("@cmd|' /C calc'!A0", obsCell.GetString());

        Assert.DoesNotContain(wb.Worksheets.SelectMany(ws => ws.CellsUsed()), c => c.HasFormula);
    }

    [Fact]
    public void Workbook_has_expected_structure()
    {
        using var wb = Export(Row("Cierre de entregables"), Row("Pruebas nocturnas"));
        Assert.Equal(["Resumen", "Detalle", "Metadatos"], wb.Worksheets.Select(w => w.Name).ToArray());

        var detail = wb.Worksheet("Detalle");
        Assert.Equal(1, detail.SheetView.SplitRow);
        Assert.Equal("Folio", detail.Cell(1, 1).GetString());
        Assert.Equal("Identificador único", detail.Cell(1, 20).GetString());

        var table = Assert.Single(detail.Tables);
        Assert.Equal("Solicitudes", table.Name);
        Assert.True(table.ShowAutoFilter);
        Assert.Equal(3, table.RangeAddress.LastAddress.RowNumber); // encabezado + 2 filas
        Assert.Equal(20, table.RangeAddress.LastAddress.ColumnNumber);

        Assert.Equal("TF-2026-000001", detail.Cell(2, 1).GetString());
        Assert.Equal(2.5, detail.Cell(2, 10).GetDouble());

        var meta = wb.Worksheet("Metadatos");
        Assert.Equal("Campo", meta.Cell(1, 1).GetString());
        Assert.Contains(meta.Column(2).CellsUsed(), c => c.GetString() == "Sofía Ramírez Castro");

        var summary = wb.Worksheet("Resumen");
        Assert.Contains(summary.Column(1).CellsUsed(), c => c.GetString() == "Total");
    }

    [Fact]
    public void Empty_export_still_has_three_sheets_and_header()
    {
        using var wb = Export();
        Assert.Equal(3, wb.Worksheets.Count);
        var detail = wb.Worksheet("Detalle");
        Assert.Empty(detail.Tables);
        Assert.Equal(1, detail.SheetView.SplitRow);
        Assert.Equal("Sin registros para los filtros seleccionados.", detail.Cell(2, 1).GetString());
    }
}

public class PdfRendererTests
{
    // PDFsharp-MigraDoc 6.2.4 (licencia MIT): no requiere registro de licencia.

    private static RequestDetailDto Detail(Guid sigId, Guid invalidSigId) => new()
    {
        Summary = new RequestSummaryDto
        {
            Id = Guid.NewGuid(), Folio = "TF-2026-000123", Kind = RequestKind.Overtime, Status = RequestStatus.Completed,
            EmployeeId = 9, EmployeeName = "Ana Torres Lozano", EmployeeNumber = "P-0100", Area = "Ingeniería de Producto",
            StartDate = new DateOnly(2026, 3, 10), EndDate = new DateOnly(2026, 3, 10), StartTime = new TimeOnly(22, 0), EndTime = new TimeOnly(1, 30),
            Hours = 3.5m, Reason = "Cierre de entregables con caracteres especiales: áéíóú ñ «»", CreatedAtUtc = new DateTime(2026, 3, 10, 15, 0, 0, DateTimeKind.Utc),
            SubmittedAtUtc = new DateTime(2026, 3, 10, 15, 5, 0, DateTimeKind.Utc), UpdatedAtUtc = new DateTime(2026, 3, 11, 15, 0, 0, DateTimeKind.Utc), Version = 2
        },
        EmployeeEmail = "ana.empleada@demo.timeflow.example", Department = "Producto", Position = "Ingeniero(a) de Producto",
        Project = "Plataforma", Activity = "Pruebas de validación", CrossesMidnight = true, SupervisorName = "Laura Hernández Vega", ManagerName = "Carlos Mendoza Ríos",
        ContentHash = new string('a', 64),
        Steps =
        [
            new ApprovalStepDto(1, ApprovalStepType.DirectSupervisor, "Jefa directa", ApprovalStepStatus.Approved, "Aprobado", "Laura Hernández Vega", "Laura Hernández Vega", DateTime.UtcNow, "Ok", 2),
            new ApprovalStepDto(2, ApprovalStepType.SeniorManager, "Jefe superior", ApprovalStepStatus.Approved, "Aprobado", "Carlos Mendoza Ríos", "Carlos Mendoza Ríos", DateTime.UtcNow, null, 2),
            new ApprovalStepDto(3, ApprovalStepType.AdministrativeRegistration, "Registro", ApprovalStepStatus.Registered, "Registrado", null, "Sofía Ramírez Castro", DateTime.UtcNow, null, 2),
        ],
        History = [new HistoryEntryDto(DateTime.UtcNow, "Envío", "Ana Torres Lozano", "Borrador", "Enviada", null, 1)],
        Signatures =
        [
            new SignatureDto(sigId, "Laura Hernández Vega", "Jefa directa", DateTime.UtcNow, 2, new string('a', 64), new string('b', 64), true, null, ElectronicSignature.SimpleElectronicSignature, null),
            new SignatureDto(invalidSigId, "Laura Hernández Vega", "Jefa directa", DateTime.UtcNow, 1, new string('c', 64), new string('d', 64), false, "Reenviada", ElectronicSignature.SimpleElectronicSignature, null),
        ],
        Administrative = new AdministrativeDto("Sofía Ramírez Castro", DateTime.UtcNow, "Sofía Ramírez Castro", DateTime.UtcNow, "Sofía Ramírez Castro", DateTime.UtcNow, "Sin observaciones", "REG-1"),
    };

    [Fact]
    public void Renders_valid_pdf_with_signature_and_qr()
    {
        var sigId = Guid.NewGuid();
        var url = "https://localhost/verificar/TF-2026-000123?c=aaaaaaaaaaaaaaaa";
        var qr = new QrCodeGeneratorService().Png(url);
        Assert.True(FileSignatures.Matches(".png", qr));

        var model = new RequestDocumentModel(Detail(sigId, Guid.NewGuid()), url, qr,
            new Dictionary<Guid, byte[]> { [sigId] = SyntheticSignature.Create(1) },
            "Documento de prueba", new DateTime(2026, 3, 12, 9, 0, 0), "Pruebas", "America/Mexico_City", "DEMO · datos sintéticos");

        var pdf = new PdfRenderer().RenderRequest(model);

        Assert.True(pdf.Length > 5 * 1024, $"PDF demasiado pequeño: {pdf.Length} bytes");
        Assert.Equal("%PDF", System.Text.Encoding.ASCII.GetString(pdf, 0, 4));
        var tail = System.Text.Encoding.ASCII.GetString(pdf, Math.Max(0, pdf.Length - 32), Math.Min(32, pdf.Length));
        Assert.Contains("%%EOF", tail);
        Assert.True(FileSignatures.Matches(".pdf", pdf));
    }

    [Fact]
    public void Renders_draft_without_steps_or_signatures()
    {
        var detail = Detail(Guid.NewGuid(), Guid.NewGuid()) with { Steps = [], Signatures = [], History = [], Administrative = null };
        var model = new RequestDocumentModel(detail, "https://localhost/v", new QrCodeGeneratorService().Png("https://localhost/v"),
            new Dictionary<Guid, byte[]>(), "", DateTime.Now, "Pruebas", "UTC", "PRUEBAS");
        var pdf = new PdfRenderer().RenderRequest(model);
        Assert.Equal("%PDF", System.Text.Encoding.ASCII.GetString(pdf, 0, 4));
    }
}
