using System.Globalization;
using System.IO.Compression;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;

namespace Gpv.Sqi.Reports;

/// <summary>
/// Exportadores CSV, XLSX (OOXML mínimo con System.IO.Compression) y HTML imprimible, sin dependencias.
/// Se neutraliza la inyección de fórmulas y todo texto HTML/XML se escapa.
/// </summary>
public static partial class Exporters
{
    private static readonly char[] FormulaPrefix = ['=', '+', '-', '@', '\t', '\r'];

    [GeneratedRegex("[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]")]
    private static partial Regex XmlIllegal();

    public static readonly Dictionary<string, (Func<UnitReport, byte[]> Func, string ContentType, string Ext)> All = new()
    {
        ["csv"] = (ToCsv, "text/csv; charset=utf-8", "csv"),
        ["xlsx"] = (ToXlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
        ["html"] = (ToHtml, "text/html; charset=utf-8", "html"),
    };

    private static string Text(object? v)
    {
        var s = v switch
        {
            null => "",
            double d => d.ToString("0.############", CultureInfo.InvariantCulture),
            bool b => b ? "True" : "False",
            _ => Convert.ToString(v, CultureInfo.InvariantCulture) ?? "",
        };
        return s.Length > 0 && FormulaPrefix.Contains(s[0]) ? "'" + s : s;
    }

    private static string CsvField(string s) =>
        s.IndexOfAny([',', '"', '\n', '\r']) >= 0 ? "\"" + s.Replace("\"", "\"\"") + "\"" : s;

    public static byte[] ToCsv(UnitReport report)
    {
        var sb = new StringBuilder();
        void Row(IEnumerable<string> cells) => sb.Append(string.Join(",", cells.Select(CsvField))).Append("\r\n");
        if (report.IsDemo) Row(["*** DATOS DE DEMOSTRACIÓN - NO SON PRODUCCIÓN ***"]);
        Row([report.Title]);
        Row([report.Disclaimer]);
        foreach (var section in report.Sections)
        {
            sb.Append("\r\n");
            Row([$"== {section.Name} =="]);
            foreach (var r in section.Rows) Row(r.Select(Text));
        }
        return Encoding.UTF8.GetPreamble().Concat(Encoding.UTF8.GetBytes(sb.ToString())).ToArray();   // BOM para Excel en español
    }

    private static string Xml(string s) => WebUtility.HtmlEncode(XmlIllegal().Replace(s, ""));

    private static string Col(int n)
    {
        var s = ""; n++;
        while (n > 0) { var r = (n - 1) % 26; s = (char)('A' + r) + s; n = (n - 1) / 26; }
        return s;
    }

    private static string SheetXml(List<List<object?>> rows)
    {
        var sb = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><sheetData>");
        for (var ri = 0; ri < rows.Count; ri++)
        {
            sb.Append($"<row r=\"{ri + 1}\">");
            for (var ci = 0; ci < rows[ri].Count; ci++)
            {
                var val = rows[ri][ci];
                var reference = $"{Col(ci)}{ri + 1}";
                var style = ri == 0 ? " s=\"1\"" : "";
                if (val is int or long or double)
                    sb.Append($"<c r=\"{reference}\"{style}><v>{Convert.ToString(val, CultureInfo.InvariantCulture)}</v></c>");
                else
                    sb.Append($"<c r=\"{reference}\" t=\"inlineStr\"{style}><is><t xml:space=\"preserve\">{Xml(Text(val))}</t></is></c>");
            }
            sb.Append("</row>");
        }
        return sb.Append("</sheetData></worksheet>").ToString();
    }

    private static string SheetName(string name, HashSet<string> used)
    {
        var b = Regex.Replace(name, @"[\[\]\*\?/\\:]", "");
        b = b.Length > 31 ? b[..31] : b;
        if (b.Length == 0) b = "Hoja";
        var o = b; var i = 2;
        while (!used.Add(o)) o = $"{(b.Length > 28 ? b[..28] : b)}_{i++}";
        return o;
    }

    public static byte[] ToXlsx(UnitReport report)
    {
        var used = new HashSet<string>();
        var sheets = new List<(string Name, List<List<object?>> Rows)>();
        foreach (var s in report.Sections)
        {
            var rows = s.Rows.ToList();
            if (s.Name == "General")
            {
                rows.Add(["Aviso", report.Disclaimer]);
                if (report.IsDemo) rows.Insert(0, ["*** DATOS DE DEMOSTRACIÓN - NO SON PRODUCCIÓN ***", ""]);
            }
            sheets.Add((SheetName(s.Name, used), rows));
        }
        using var ms = new MemoryStream();
        using (var zip = new ZipArchive(ms, ZipArchiveMode.Create, true))
        {
            void Put(string path, string content)
            {
                var e = zip.CreateEntry(path, CompressionLevel.Optimal);
                using var w = new StreamWriter(e.Open(), new UTF8Encoding(false));
                w.Write(content);
            }
            var ct = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">" +
                "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/>" +
                "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>" +
                "<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>");
            for (var i = 1; i <= sheets.Count; i++)
                ct.Append($"<Override PartName=\"/xl/worksheets/sheet{i}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>");
            Put("[Content_Types].xml", ct.Append("</Types>").ToString());
            Put("_rels/.rels", "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">" +
                "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/></Relationships>");
            var wb = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" " +
                "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets>");
            var rels = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">");
            for (var i = 1; i <= sheets.Count; i++)
            {
                wb.Append($"<sheet name=\"{Xml(sheets[i - 1].Name)}\" sheetId=\"{i}\" r:id=\"rId{i}\"/>");
                rels.Append($"<Relationship Id=\"rId{i}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet{i}.xml\"/>");
            }
            rels.Append($"<Relationship Id=\"rId{sheets.Count + 1}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>");
            Put("xl/workbook.xml", wb.Append("</sheets></workbook>").ToString());
            Put("xl/_rels/workbook.xml.rels", rels.Append("</Relationships>").ToString());
            Put("xl/styles.xml", "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">" +
                "<fonts count=\"2\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font><font><b/><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>" +
                "<fills count=\"2\"><fill><patternFill patternType=\"none\"/></fill><fill><patternFill patternType=\"gray125\"/></fill></fills>" +
                "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>" +
                "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>" +
                "<cellXfs count=\"2\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/><xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyFont=\"1\"/></cellXfs></styleSheet>");
            for (var i = 1; i <= sheets.Count; i++) Put($"xl/worksheets/sheet{i}.xml", SheetXml(sheets[i - 1].Rows));
        }
        return ms.ToArray();
    }

    public static byte[] ToHtml(UnitReport report)
    {
        static string E(object? v) => WebUtility.HtmlEncode(v switch
        {
            null => "",
            double d => d.ToString("0.############", CultureInfo.InvariantCulture),
            _ => Convert.ToString(v, CultureInfo.InvariantCulture) ?? "",
        });
        var sb = new StringBuilder("<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">");
        sb.Append($"<title>{E(report.Title)}</title>");
        sb.Append("<style>body{font-family:Segoe UI,Arial,sans-serif;color:#1b2430;margin:24px;font-size:12px}h1{font-size:20px;margin:0 0 4px}" +
                  "h2{font-size:14px;margin:20px 0 6px;border-bottom:2px solid #0a4f9e;padding-bottom:3px;color:#0a4f9e}table{border-collapse:collapse;width:100%;margin-bottom:8px}" +
                  "th,td{border:1px solid #c9d1db;padding:4px 6px;text-align:left;vertical-align:top}th{background:#eef2f7}" +
                  ".demo{background:#c2410c;color:#fff;padding:8px;font-weight:700;margin-bottom:10px}" +
                  ".disc{border-left:4px solid #b45309;background:#fff7ed;padding:8px;margin:10px 0;font-weight:600}@media print{body{margin:10mm}}</style></head><body>");
        if (report.IsDemo) sb.Append("<div class=\"demo\">DATOS DE DEMOSTRACIÓN — NO SON PRODUCCIÓN</div>");
        sb.Append($"<h1>{E(report.Title)}</h1><div>GPV Americas E-MXG · GPV SMT Quality Intelligence</div>");
        sb.Append($"<div class=\"disc\">{E(report.Disclaimer)}</div>");
        foreach (var s in report.Sections)
        {
            sb.Append($"<h2>{E(s.Name)}</h2>");
            if (s.Rows.Count == 0 || (s.Rows.Count == 1 && s.Name != "General")) { sb.Append("<p>Sin registros.</p>"); continue; }
            sb.Append("<table>");
            if (s.Name == "General")
                foreach (var r in s.Rows) sb.Append($"<tr><th>{E(r[0])}</th><td>{E(r[1])}</td></tr>");
            else
            {
                sb.Append("<tr>").Append(string.Concat(s.Rows[0].Select(c => $"<th>{E(c)}</th>"))).Append("</tr>");
                foreach (var r in s.Rows.Skip(1)) sb.Append("<tr>").Append(string.Concat(r.Select(c => $"<td>{E(c)}</td>"))).Append("</tr>");
            }
            sb.Append("</table>");
        }
        return Encoding.UTF8.GetBytes(sb.Append("</body></html>").ToString());
    }
}
