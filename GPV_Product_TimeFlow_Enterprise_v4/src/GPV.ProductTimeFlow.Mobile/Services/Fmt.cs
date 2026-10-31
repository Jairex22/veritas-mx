using System.Globalization;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>Formatos de fecha/hora/cantidades en español de México. Las fechas UTC de la API se muestran en hora local.</summary>
public static class Fmt
{
    public static readonly CultureInfo Culture = CultureInfo.GetCultureInfo("es-MX");

    public static DateOnly Today => DateOnly.FromDateTime(DateTime.Now);

    public static string Date(DateOnly date) => date.ToString("d MMM yyyy", Culture);

    public static string DateLong(DateOnly date) => Capitalize(date.ToString("dddd d 'de' MMMM yyyy", Culture));

    public static string Time(TimeOnly time) => time.ToString("HH:mm", Culture);

    public static string Local(DateTime utc) => ToLocal(utc).ToString("d MMM yyyy, HH:mm", Culture);

    public static string Relative(DateTime utc)
    {
        var local = ToLocal(utc);
        var delta = DateTime.Now - local;
        if (delta < TimeSpan.FromMinutes(1)) return "hace un momento";
        if (delta < TimeSpan.FromHours(1)) return $"hace {(int)delta.TotalMinutes} min";
        if (delta < TimeSpan.FromDays(1) && local.Date == DateTime.Today) return $"hoy, {local:HH:mm}";
        if (local.Date == DateTime.Today.AddDays(-1)) return $"ayer, {local:HH:mm}";
        return local.ToString("d MMM yyyy", Culture);
    }

    public static string MonthTitle(int year, int month) => Capitalize(new DateTime(year, month, 1).ToString("MMMM yyyy", Culture));

    public static string Number(decimal value) => value.ToString("0.##", Culture);

    /// <summary>Periodo de una solicitud: fecha + horario (tiempo extra / permiso parcial) o rango de días.</summary>
    public static string Period(RequestSummaryDto r)
    {
        if (r.StartTime is { } start && r.EndTime is { } end && (r.Kind == RequestKind.Overtime || !r.IsFullDay))
            return $"{Date(r.StartDate)} · {Time(start)}–{Time(end)}";
        return r.EndDate > r.StartDate ? $"{Date(r.StartDate)} – {Date(r.EndDate)}" : Date(r.StartDate);
    }

    /// <summary>Cantidad principal: horas para tiempo extra y permisos parciales; días en lo demás.</summary>
    public static string Amount(RequestSummaryDto r) =>
        r.Kind == RequestKind.Overtime || (!r.IsFullDay && r.Hours > 0) ? Labels.Hours(r.Hours) : Labels.Days(r.Days);

    public static string FileSize(long bytes) => bytes switch
    {
        < 1024 => $"{bytes} B",
        < 1024 * 1024 => $"{bytes / 1024d:0.#} KB",
        _ => $"{bytes / (1024d * 1024d):0.#} MB",
    };

    public static string Initials(string? name)
    {
        if (string.IsNullOrWhiteSpace(name)) return "?";
        var parts = name.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        return parts.Length == 1 ? parts[0][..1].ToUpper(Culture) : $"{parts[0][0]}{parts[^1][0]}".ToUpper(Culture);
    }

    private static DateTime ToLocal(DateTime utc) =>
        (utc.Kind == DateTimeKind.Unspecified ? DateTime.SpecifyKind(utc, DateTimeKind.Utc) : utc).ToLocalTime();

    private static string Capitalize(string text) => text.Length == 0 ? text : char.ToUpper(text[0], Culture) + text[1..];
}
