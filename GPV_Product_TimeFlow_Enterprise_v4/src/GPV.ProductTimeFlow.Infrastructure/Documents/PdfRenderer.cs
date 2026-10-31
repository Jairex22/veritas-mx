using System.Globalization;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Shared;
using MigraDoc.DocumentObjectModel;
using MigraDoc.DocumentObjectModel.Tables;
using MigraDoc.Rendering;
using PdfSharp.Fonts;

namespace GPV.ProductTimeFlow.Infrastructure.Documents;

/// <summary>Resolución de fuentes embebidas (Liberation Sans, licencia SIL OFL 1.1) para un PDF idéntico en Windows y Linux.</summary>
internal sealed class EmbeddedFontResolver : IFontResolver
{
    private static readonly object Gate = new();
    private static bool _registered;

    public static void EnsureRegistered()
    {
        lock (Gate)
        {
            if (_registered) return;
            GlobalFontSettings.FontResolver = new EmbeddedFontResolver();
            _registered = true;
        }
    }

    public FontResolverInfo ResolveTypeface(string familyName, bool isBold, bool isItalic) =>
        new(isBold ? "LiberationSans-Bold" : isItalic ? "LiberationSans-Italic" : "LiberationSans-Regular");

    public byte[] GetFont(string faceName)
    {
        var asm = typeof(EmbeddedFontResolver).Assembly;
        var name = asm.GetManifestResourceNames().First(n => n.EndsWith(faceName + ".ttf", StringComparison.Ordinal));
        using var stream = asm.GetManifestResourceStream(name)!;
        using var ms = new MemoryStream();
        stream.CopyTo(ms);
        return ms.ToArray();
    }
}

/// <summary>
/// Formato imprimible tamaño carta del expediente. Plantilla en código (MigraDoc, MIT) para adaptarse a formatos
/// oficiales futuros modificando solo este archivo.
/// </summary>
public sealed class PdfRenderer : IPdfRenderer
{
    private static readonly Color Ink = new(17, 24, 39);
    private static readonly Color Muted = new(107, 114, 128);
    private static readonly Color Line = new(229, 231, 235);
    private static readonly Color Soft = new(246, 247, 251);
    private static readonly CultureInfo Es = CultureInfo.GetCultureInfo("es-MX");

    public byte[] RenderRequest(RequestDocumentModel m)
    {
        EmbeddedFontResolver.EnsureRegistered();
        var d = m.Detail;
        var s = d.Summary;
        var brand = new Color(31, 79, 216);

        var doc = new Document();
        doc.Info.Title = $"Expediente {s.Folio}";
        doc.Info.Author = "GPV Product TimeFlow";
        doc.Info.Subject = Labels.Kind(s.Kind);
        var normal = doc.Styles[StyleNames.Normal]!;
        normal.Font.Name = "Liberation Sans";
        normal.Font.Size = 9;
        normal.Font.Color = Ink;

        var section = doc.AddSection();
        var ps = section.PageSetup;
        ps.PageFormat = PageFormat.Letter;
        ps.TopMargin = Unit.FromCentimeter(2.6);
        ps.BottomMargin = Unit.FromCentimeter(2.0);
        ps.LeftMargin = ps.RightMargin = Unit.FromCentimeter(1.8);
        ps.HeaderDistance = Unit.FromCentimeter(0.9);
        ps.FooterDistance = Unit.FromCentimeter(0.8);

        // Encabezado
        var header = section.Headers.Primary.AddTable();
        header.AddColumn(Unit.FromCentimeter(11.5));
        header.AddColumn(Unit.FromCentimeter(6.4));
        var hr = header.AddRow();
        var title = hr.Cells[0].AddParagraph();
        title.AddFormattedText("GPV Product TimeFlow", new Font { Bold = true, Size = 13, Color = brand });
        title.AddLineBreak();
        title.AddFormattedText("Expediente de solicitud · Departamento de Producto", new Font { Size = 8, Color = Muted });
        var right = hr.Cells[1].AddParagraph();
        right.Format.Alignment = ParagraphAlignment.Right;
        right.AddFormattedText($"Folio {s.Folio}", new Font { Bold = true, Size = 11 });
        right.AddLineBreak();
        right.AddFormattedText(m.EnvironmentLabel, new Font { Size = 7.5, Color = m.EnvironmentLabel.StartsWith("PRODUCCIÓN", StringComparison.Ordinal) ? Muted : new Color(180, 83, 9), Bold = true });
        hr.Borders.Bottom = new Border { Width = 1.2, Color = brand };
        hr.BottomPadding = Unit.FromPoint(6);

        // Pie
        var footer = section.Footers.Primary.AddParagraph();
        footer.Format.Font.Size = 7;
        footer.Format.Font.Color = Muted;
        footer.AddText($"{m.FooterText}  ·  Generado {m.GeneratedAtLocal.ToString("dd/MM/yyyy HH:mm", Es)} ({m.TimeZoneLabel}) por {m.GeneratedBy}  ·  Página ");
        footer.AddPageField();
        footer.AddText(" de ");
        footer.AddNumPagesField();

        // Título y estado
        var h = section.AddParagraph(Labels.Kind(s.Kind));
        h.Format.Font.Size = 16; h.Format.Font.Bold = true; h.Format.SpaceAfter = Unit.FromPoint(2);
        var st = section.AddParagraph();
        st.AddFormattedText("Estado: ", new Font { Color = Muted });
        st.AddFormattedText(s.StatusLabel, new Font { Bold = true });
        st.AddFormattedText($"   ·   Versión revisada: {s.Version}", new Font { Color = Muted });
        st.Format.SpaceAfter = Unit.FromPoint(10);

        SectionTitle(section, "Datos del empleado");
        KeyValues(section,
            ("Nombre", s.EmployeeName), ("Número de empleado", s.EmployeeNumber),
            ("Departamento", d.Department ?? "Producto"), ("Área", s.Area ?? "—"),
            ("Puesto", d.Position ?? "—"), ("Correo", d.EmployeeEmail ?? "—"));

        SectionTitle(section, "Detalle de la solicitud");
        var dates = s.Kind == RequestKind.Overtime || !s.IsFullDay
            ? $"{s.StartDate.ToString("dddd dd 'de' MMMM yyyy", Es)}, {s.StartTime:HH\\:mm} a {s.EndTime:HH\\:mm}{(d.CrossesMidnight ? " (día siguiente)" : "")}"
            : s.StartDate == s.EndDate ? s.StartDate.ToString("dddd dd 'de' MMMM yyyy", Es)
            : $"{s.StartDate.ToString("dd/MM/yyyy", Es)} al {s.EndDate.ToString("dd/MM/yyyy", Es)}";
        var duration = s.Kind == RequestKind.Overtime || !s.IsFullDay ? Labels.Hours(s.Hours) : Labels.Days(s.Days) + " hábiles";
        var pairs = new List<(string, string)> { ("Tipo", Labels.Kind(s.Kind)), ("Fechas", dates), ("Duración", duration), ("Fecha de envío", Local(s.SubmittedAtUtc, m)) };
        if (s.Kind == RequestKind.Overtime) { pairs.Add(("Proyecto", d.Project ?? "—")); pairs.Add(("Actividad", d.Activity ?? "—")); }
        if (d.LeaveCategoryName is not null) pairs.Add(("Clasificación", d.LeaveCategoryName));
        if (s.Kind == RequestKind.UnpaidLeave) pairs.Add(("Aviso", "Permiso SIN goce de sueldo. Esta aplicación no aplica descuentos de nómina."));
        pairs.Add(("Motivo", s.Reason));
        if (d.Justification is not null) pairs.Add(("Justificación", d.Justification));
        if (d.Observations is not null) pairs.Add(("Observaciones", d.Observations));
        if (d.Attachments.Count > 0) pairs.Add(("Adjuntos", string.Join(", ", d.Attachments.Select(a => a.FileName))));
        KeyValues(section, [.. pairs]);

        SectionTitle(section, "Autorizaciones");
        var t = Table(section, [4.2, 4.6, 3.2, 3.0, 2.9]);
        HeaderRow(t, "Filtro", "Responsable", "Resultado", "Fecha", "Versión");
        foreach (var step in d.Steps)
            Row(t, step.TypeLabel, step.ActorName ?? step.AssigneeName ?? "—", step.StatusLabel, Local(step.ActedAtUtc, m), step.RequestVersion.ToString(Es));
        if (d.Steps.Count == 0) Row(t, "Sin envío", "—", "—", "—", "—");

        SectionTitle(section, "Firmas y constancias de autorización");
        var valid = d.Signatures.Where(x => x.IsValid && x.RequestVersion == s.Version).ToList();
        if (valid.Count == 0)
        {
            Note(section, "No hay firmas vigentes para la versión actual de la solicitud.");
        }
        else
        {
            var sig = Table(section, [5.0, 12.9]);
            foreach (var g in valid)
            {
                var row = sig.AddRow();
                row.VerticalAlignment = VerticalAlignment.Center;
                row.TopPadding = row.BottomPadding = Unit.FromPoint(4);
                if (m.SignatureImages.TryGetValue(g.Id, out var png) && png.Length > 0)
                {
                    var img = row.Cells[0].AddImage("base64:" + Convert.ToBase64String(png));
                    img.Width = Unit.FromCentimeter(4.4);
                    img.LockAspectRatio = true;
                }
                var p = row.Cells[1].AddParagraph();
                p.AddFormattedText($"{g.SignerName} — {g.SignerRole}", new Font { Bold = true });
                p.AddLineBreak();
                p.AddText($"Firmado: {Local(g.SignedAtUtc, m)} · Versión {g.RequestVersion}");
                p.AddLineBreak();
                p.AddFormattedText($"Huella del documento (SHA-256): {g.DocumentHash}", new Font { Size = 6.5, Color = Muted });
                p.AddLineBreak();
                p.AddFormattedText($"Huella de la firma: {g.SignatureHash}", new Font { Size = 6.5, Color = Muted });
                p.AddLineBreak();
                p.AddFormattedText(g.SignatureType, new Font { Size = 7, Color = Muted, Italic = true });
            }
        }
        var invalid = d.Signatures.Count(x => !x.IsValid);
        if (invalid > 0) Note(section, $"{invalid} firma(s) de versiones anteriores fueron invalidadas por cambios o reenvío y no forman parte de esta constancia.");

        SectionTitle(section, "Registro administrativo");
        var a = d.Administrative;
        KeyValues(section,
            ("Recibida", a?.ReceivedAtUtc is null ? "Pendiente" : $"{Local(a.ReceivedAtUtc, m)} · {a.ReceivedByName}"),
            ("Registrada", a?.RegisteredAtUtc is null ? "Pendiente" : $"{Local(a.RegisteredAtUtc, m)} · {a.RegisteredByName}"),
            ("Procesada", a?.ProcessedAtUtc is null ? "Pendiente" : $"{Local(a.ProcessedAtUtc, m)} · {a.ProcessedByName}"),
            ("Referencia", a?.ExternalReference ?? "—"),
            ("Observaciones", a?.Observations ?? "—"));

        SectionTitle(section, "Historial resumido");
        var hist = Table(section, [3.4, 5.6, 4.6, 4.3]);
        HeaderRow(hist, "Fecha", "Acción", "Responsable", "Estado resultante");
        foreach (var e in d.History.TakeLast(14)) Row(hist, Local(e.OccurredAtUtc, m), e.ActionLabel, e.ActorName, e.ToStatusLabel ?? "—");

        // Verificación
        section.AddParagraph().Format.SpaceAfter = Unit.FromPoint(6);
        var v = Table(section, [3.4, 14.5]);
        v.Borders.Visible = false;
        var vr = v.AddRow();
        vr.Shading.Color = Soft;
        vr.VerticalAlignment = VerticalAlignment.Center;
        var qr = vr.Cells[0].AddImage("base64:" + Convert.ToBase64String(m.QrPng));
        qr.Width = Unit.FromCentimeter(3.0);
        qr.LockAspectRatio = true;
        var vp = vr.Cells[1].AddParagraph();
        vp.AddFormattedText("Verificación de autenticidad", new Font { Bold = true });
        vp.AddLineBreak();
        vp.AddText("Escanee el código o visite la dirección para comprobar que este documento corresponde a la versión registrada:");
        vp.AddLineBreak();
        vp.AddFormattedText(m.VerificationUrl, new Font { Size = 7.5, Color = brand });
        vp.AddLineBreak();
        vp.AddFormattedText($"Huella SHA-256 de la versión {s.Version}: {d.ContentHash}", new Font { Size = 6.5, Color = Muted });
        vp.AddLineBreak();
        vp.AddFormattedText("Las firmas de este formato son firmas electrónicas simples (trazo capturado tras autenticación). No constituyen firma electrónica avanzada ni firma digital criptográfica con certificado.",
            new Font { Size = 7, Italic = true, Color = Muted });

        var renderer = new PdfDocumentRenderer { Document = doc };
        renderer.RenderDocument();
        using var ms = new MemoryStream();
        renderer.PdfDocument.Save(ms, false);
        return ms.ToArray();
    }

    private static string Local(DateTime? utc, RequestDocumentModel m)
    {
        if (utc is null) return "—";
        try
        {
            var zone = TimeZoneInfo.FindSystemTimeZoneById(m.TimeZoneLabel);
            return TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc.Value, DateTimeKind.Utc), zone).ToString("dd/MM/yyyy HH:mm", Es);
        }
        catch (TimeZoneNotFoundException) { return utc.Value.ToString("dd/MM/yyyy HH:mm 'UTC'", Es); }
    }

    private static void SectionTitle(Section section, string text)
    {
        var p = section.AddParagraph(text.ToUpper(Es));
        p.Format.Font.Size = 8;
        p.Format.Font.Bold = true;
        p.Format.Font.Color = Muted;
        p.Format.SpaceBefore = Unit.FromPoint(12);
        p.Format.SpaceAfter = Unit.FromPoint(4);
        p.Format.KeepWithNext = true;
    }

    private static void Note(Section section, string text)
    {
        var p = section.AddParagraph(text);
        p.Format.Font.Size = 8;
        p.Format.Font.Italic = true;
        p.Format.Font.Color = Muted;
        p.Format.SpaceBefore = Unit.FromPoint(3);
    }

    private static Table Table(Section section, double[] widthsCm)
    {
        var t = section.AddTable();
        t.Borders.Color = Line;
        t.Borders.Width = 0.5;
        t.LeftPadding = t.RightPadding = Unit.FromPoint(5);
        t.TopPadding = t.BottomPadding = Unit.FromPoint(3);
        foreach (var w in widthsCm) t.AddColumn(Unit.FromCentimeter(w));
        return t;
    }

    private static void HeaderRow(Table t, params string[] cells)
    {
        var r = t.AddRow();
        r.HeadingFormat = true;
        r.Shading.Color = Soft;
        for (var i = 0; i < cells.Length; i++)
        {
            var p = r.Cells[i].AddParagraph(cells[i]);
            p.Format.Font.Bold = true;
            p.Format.Font.Size = 8;
        }
    }

    private static void Row(Table t, params string[] cells)
    {
        var r = t.AddRow();
        for (var i = 0; i < cells.Length; i++) r.Cells[i].AddParagraph(cells[i] ?? "—");
    }

    private static void KeyValues(Section section, params (string Key, string Value)[] pairs)
    {
        var t = Table(section, [4.2, 13.7]);
        foreach (var (k, v) in pairs)
        {
            var r = t.AddRow();
            r.Cells[0].Shading.Color = Soft;
            var kp = r.Cells[0].AddParagraph(k);
            kp.Format.Font.Color = Muted;
            r.Cells[1].AddParagraph(string.IsNullOrWhiteSpace(v) ? "—" : v);
        }
    }
}
