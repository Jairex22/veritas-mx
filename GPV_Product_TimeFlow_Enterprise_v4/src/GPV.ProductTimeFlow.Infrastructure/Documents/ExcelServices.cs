using System.Globalization;
using ClosedXML.Excel;
using GPV.ProductTimeFlow.Application;

namespace GPV.ProductTimeFlow.Infrastructure.Documents;

/// <summary>Exportación profesional con ClosedXML (MIT): hoja de resumen, detalle (tabla con filtros) y metadatos.</summary>
public sealed class ExcelExporter : IExcelExporter
{
    private static readonly XLColor Header = XLColor.FromHtml("#1F2A44");
    private static readonly XLColor Band = XLColor.FromHtml("#F4F6FB");
    private static readonly XLColor Accent = XLColor.FromHtml("#1F4FD8");

    /// <summary>
    /// Neutraliza la inyección de fórmulas (CSV/Excel injection): los textos que empiezan con = + - @ tab o CR
    /// se guardan como texto con prefijo de comilla (QuotePrefix), nunca como fórmula.
    /// </summary>
    internal static void SetSafeText(IXLCell cell, string? value)
    {
        var v = value ?? "";
        cell.SetValue(v);
        if (v.Length > 0 && v[0] is '=' or '+' or '-' or '@' or '\t' or '\r') cell.Style.IncludeQuotePrefix = true;
    }

    public byte[] ExportRequests(IReadOnlyList<ExportRow> rows, ExportMetadata metadata)
    {
        using var wb = new XLWorkbook();
        wb.Properties.Author = "GPV Product TimeFlow";
        wb.Properties.Title = "Exportación de solicitudes autorizadas";

        // ── Resumen ──
        var summary = wb.Worksheets.Add("Resumen");
        summary.Cell("A1").Value = "GPV Product TimeFlow · Exportación para registro administrativo";
        summary.Cell("A1").Style.Font.SetBold().Font.SetFontSize(14).Font.SetFontColor(Accent);
        summary.Cell("A2").Value = $"Generado {metadata.GeneratedAtLocal:dd/MM/yyyy HH:mm} ({metadata.TimeZone}) por {metadata.GeneratedBy} · {metadata.EnvironmentLabel}";
        summary.Cell("A2").Style.Font.SetFontColor(XLColor.Gray);
        summary.Cell("A4").Value = "Tipo de solicitud";
        summary.Cell("B4").Value = "Solicitudes";
        summary.Cell("C4").Value = "Horas";
        summary.Cell("D4").Value = "Días";
        StyleHeader(summary.Range("A4:D4"));
        var r = 5;
        foreach (var g in rows.GroupBy(x => x.Type).OrderBy(g => g.Key))
        {
            SetSafeText(summary.Cell(r, 1), g.Key);
            summary.Cell(r, 2).Value = g.Count();
            summary.Cell(r, 3).Value = g.Sum(x => x.Hours);
            summary.Cell(r, 4).Value = g.Sum(x => x.Days);
            r++;
        }
        summary.Cell(r, 1).Value = "Total";
        summary.Cell(r, 2).Value = rows.Count;
        summary.Cell(r, 3).Value = rows.Sum(x => x.Hours);
        summary.Cell(r, 4).Value = rows.Sum(x => x.Days);
        summary.Range(r, 1, r, 4).Style.Font.SetBold().Border.SetTopBorder(XLBorderStyleValues.Thin);
        summary.Range(5, 3, r, 4).Style.NumberFormat.Format = "0.00";
        r += 2;
        summary.Cell(r, 1).Value = "Por estado";
        summary.Cell(r, 2).Value = "Solicitudes";
        StyleHeader(summary.Range(r, 1, r, 2));
        r++;
        foreach (var g in rows.GroupBy(x => x.AdministrativeStatus).OrderBy(g => g.Key))
        {
            SetSafeText(summary.Cell(r, 1), g.Key);
            summary.Cell(r, 2).Value = g.Count();
            r++;
        }
        summary.Columns(1, 4).AdjustToContents();
        summary.Column(1).Width = Math.Max(summary.Column(1).Width, 34);

        // ── Detalle ──
        var detail = wb.Worksheets.Add("Detalle");
        string[] headers =
        [
            "Folio", "Fecha de creación", "Número de empleado", "Nombre", "Departamento", "Área", "Tipo", "Fecha inicial", "Fecha final",
            "Horas", "Días", "Motivo", "Jefa directa", "Fecha aprobación jefa", "Jefe superior", "Fecha aprobación superior",
            "Estado administrativo", "Fecha registro", "Observaciones", "Identificador único"
        ];
        for (var c = 0; c < headers.Length; c++) detail.Cell(1, c + 1).Value = headers[c];
        var i = 2;
        foreach (var x in rows)
        {
            SetSafeText(detail.Cell(i, 1), x.Folio);
            detail.Cell(i, 2).Value = x.CreatedAtLocal;
            SetSafeText(detail.Cell(i, 3), x.EmployeeNumber);
            SetSafeText(detail.Cell(i, 4), x.EmployeeName);
            SetSafeText(detail.Cell(i, 5), x.Department);
            SetSafeText(detail.Cell(i, 6), x.Area);
            SetSafeText(detail.Cell(i, 7), x.Type);
            detail.Cell(i, 8).Value = x.StartDate.ToDateTime(TimeOnly.MinValue);
            detail.Cell(i, 9).Value = x.EndDate.ToDateTime(TimeOnly.MinValue);
            detail.Cell(i, 10).Value = x.Hours;
            detail.Cell(i, 11).Value = x.Days;
            SetSafeText(detail.Cell(i, 12), x.Reason);
            SetSafeText(detail.Cell(i, 13), x.SupervisorName);
            if (x.SupervisorApprovedAtLocal is DateTime sa) detail.Cell(i, 14).Value = sa;
            SetSafeText(detail.Cell(i, 15), x.ManagerName);
            if (x.ManagerApprovedAtLocal is DateTime ma) detail.Cell(i, 16).Value = ma;
            SetSafeText(detail.Cell(i, 17), x.AdministrativeStatus);
            if (x.RegisteredAtLocal is DateTime ra) detail.Cell(i, 18).Value = ra;
            SetSafeText(detail.Cell(i, 19), x.Observations);
            SetSafeText(detail.Cell(i, 20), x.Id.ToString());
            i++;
        }
        var last = Math.Max(2, i - 1);
        if (rows.Count > 0)
        {
            var table = detail.Range(1, 1, last, headers.Length).CreateTable("Solicitudes");
            table.Theme = XLTableTheme.TableStyleLight9;
            table.ShowAutoFilter = true;
        }
        else
        {
            StyleHeader(detail.Range(1, 1, 1, headers.Length));
            detail.Cell(2, 1).Value = "Sin registros para los filtros seleccionados.";
        }
        detail.Column(2).Style.NumberFormat.Format = "dd/mm/yyyy hh:mm";
        foreach (var c in new[] { 8, 9 }) detail.Column(c).Style.NumberFormat.Format = "dd/mm/yyyy";
        foreach (var c in new[] { 14, 16, 18 }) detail.Column(c).Style.NumberFormat.Format = "dd/mm/yyyy hh:mm";
        foreach (var c in new[] { 10, 11 }) detail.Column(c).Style.NumberFormat.Format = "0.00";
        detail.SheetView.FreezeRows(1);
        detail.Columns().AdjustToContents(1, Math.Min(last, 300), 10, 60);
        detail.Column(12).Width = 45; detail.Column(19).Width = 45;
        detail.Column(12).Style.Alignment.WrapText = false;

        // ── Metadatos ──
        var meta = wb.Worksheets.Add("Metadatos");
        var items = new (string, string)[]
        {
            ("Sistema", "GPV Product TimeFlow Enterprise 4.0.0"),
            ("Propietario funcional", "Departamento de Producto · GPV Americas"),
            ("Generado por", metadata.GeneratedBy),
            ("Fecha de generación", metadata.GeneratedAtLocal.ToString("dd/MM/yyyy HH:mm:ss", CultureInfo.InvariantCulture)),
            ("Zona horaria", metadata.TimeZone),
            ("Ambiente", metadata.EnvironmentLabel),
            ("Filtros", metadata.Filters),
            ("Registros", rows.Count.ToString(CultureInfo.InvariantCulture)),
            ("Naturaleza", "Exportación de solo lectura. No modifica la base de datos ni sustituye el registro administrativo oficial."),
            ("Privacidad", "Contiene datos personales de empleados. Manéjese conforme a la política de protección de datos de GPV."),
        };
        meta.Cell(1, 1).Value = "Campo"; meta.Cell(1, 2).Value = "Valor";
        StyleHeader(meta.Range(1, 1, 1, 2));
        for (var k = 0; k < items.Length; k++) { SetSafeText(meta.Cell(k + 2, 1), items[k].Item1); SetSafeText(meta.Cell(k + 2, 2), items[k].Item2); }
        meta.Column(1).Width = 24; meta.Column(2).Width = 100;

        summary.SetTabActive();
        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }

    public byte[] EmployeeImportTemplate()
    {
        using var wb = new XLWorkbook();
        var ws = wb.Worksheets.Add("Empleados");
        string[] headers = ["NumeroEmpleado", "NombreCompleto", "Correo", "Departamento", "Area", "Puesto", "CorreoJefaDirecta", "CorreoJefeSuperior", "Roles", "FechaIngreso", "DiasVacaciones"];
        for (var c = 0; c < headers.Length; c++) ws.Cell(1, c + 1).Value = headers[c];
        StyleHeader(ws.Range(1, 1, 1, headers.Length));
        object[] example = ["P-9001", "Nombre Sintético Ejemplo", "nombre.ejemplo@demo.timeflow.example", "Producto", "Ingeniería de Producto", "Ingeniero(a) de Producto", "laura.jefa@demo.timeflow.example", "carlos.superior@demo.timeflow.example", "Empleado", new DateTime(2022, 3, 1), 14];
        for (var c = 0; c < example.Length; c++) ws.Cell(2, c + 1).Value = XLCellValue.FromObject(example[c]);
        ws.Column(10).Style.NumberFormat.Format = "dd/mm/yyyy";
        ws.SheetView.FreezeRows(1);
        ws.Columns().AdjustToContents();
        var help = wb.Worksheets.Add("Instrucciones");
        string[] lines =
        [
            "Instrucciones de importación controlada",
            "1. No cambie los encabezados de la hoja «Empleados». Una fila por empleado.",
            "2. NumeroEmpleado y Correo deben ser únicos; si el número ya existe, el registro se actualiza.",
            "3. Roles: Empleado, Jefa directa, Jefe superior, Administrador de Producto, Registro administrativo (separados por coma).",
            "4. CorreoJefaDirecta y CorreoJefeSuperior deben existir en el sistema o en el mismo archivo.",
            "5. Ejecute primero «Validar (simulación)»: no se guarda nada hasta confirmar la importación.",
            "6. Use únicamente datos autorizados. No incluya contraseñas."
        ];
        for (var k = 0; k < lines.Length; k++) help.Cell(k + 1, 1).Value = lines[k];
        help.Cell(1, 1).Style.Font.SetBold().Font.SetFontSize(13);
        help.Column(1).Width = 110;
        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }

    private static void StyleHeader(IXLRange range)
    {
        range.Style.Font.SetBold().Font.SetFontColor(XLColor.White).Fill.SetBackgroundColor(Header);
        range.Style.Alignment.SetVertical(XLAlignmentVerticalValues.Center);
        _ = Band;
    }
}

public sealed class ExcelImporter : IExcelImporter
{
    public IReadOnlyList<EmployeeImportRow> ReadEmployees(Stream workbook)
    {
        using var wb = new XLWorkbook(workbook);
        var ws = wb.Worksheets.FirstOrDefault(w => w.Name.Equals("Empleados", StringComparison.OrdinalIgnoreCase)) ?? wb.Worksheet(1);
        var headerRow = ws.Row(1);
        var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var cell in headerRow.CellsUsed()) map[cell.GetString().Trim()] = cell.Address.ColumnNumber;
        string[] required = ["NumeroEmpleado", "NombreCompleto", "Correo"];
        var missing = required.Where(r => !map.ContainsKey(r)).ToList();
        if (missing.Count > 0) throw new BusinessRuleException($"Faltan columnas obligatorias: {string.Join(", ", missing)}.");

        string? Get(IXLRow row, string name) => map.TryGetValue(name, out var c) ? Text.Clean(row.Cell(c).GetFormattedString()) : null;
        var result = new List<EmployeeImportRow>();
        foreach (var row in ws.RowsUsed().Skip(1))
        {
            if (row.CellsUsed().All(c => string.IsNullOrWhiteSpace(c.GetString()))) continue;
            DateOnly? hire = null;
            if (map.TryGetValue("FechaIngreso", out var hc))
            {
                var cell = row.Cell(hc);
                if (cell.DataType == XLDataType.DateTime) hire = DateOnly.FromDateTime(cell.GetDateTime());
                else if (DateOnly.TryParseExact(cell.GetString(), ["dd/MM/yyyy", "yyyy-MM-dd"], CultureInfo.InvariantCulture, DateTimeStyles.None, out var d)) hire = d;
            }
            decimal? days = null;
            if (map.TryGetValue("DiasVacaciones", out var dc) && decimal.TryParse(row.Cell(dc).GetString(), NumberStyles.Number, CultureInfo.InvariantCulture, out var dv)) days = dv;
            result.Add(new EmployeeImportRow(row.RowNumber(), Get(row, "NumeroEmpleado"), Get(row, "NombreCompleto"), Get(row, "Correo"), Get(row, "Departamento"),
                Get(row, "Area"), Get(row, "Puesto"), Get(row, "CorreoJefaDirecta"), Get(row, "CorreoJefeSuperior"), Get(row, "Roles"), hire, days));
        }
        return result;
    }
}
