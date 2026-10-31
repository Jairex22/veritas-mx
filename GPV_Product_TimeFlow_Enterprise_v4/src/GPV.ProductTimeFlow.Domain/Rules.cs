using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.Domain;

public sealed record OvertimeCalculation(DateTime StartLocal, DateTime EndLocal, decimal Hours, bool CrossesMidnight);

/// <summary>Cálculo de horas de tiempo extra. No calcula conceptos de nómina.</summary>
public static class OvertimeCalculator
{
    /// <summary>
    /// Calcula la duración. Si la hora final es menor o igual que la inicial se interpreta como
    /// cruce de medianoche (termina al día siguiente). Resultado redondeado a 2 decimales.
    /// </summary>
    public static OvertimeCalculation Calculate(DateOnly date, TimeOnly start, TimeOnly end)
    {
        var startLocal = date.ToDateTime(start);
        var crosses = end <= start;
        var endLocal = (crosses ? date.AddDays(1) : date).ToDateTime(end);
        var hours = Math.Round((decimal)(endLocal - startLocal).TotalMinutes / 60m, 2, MidpointRounding.AwayFromZero);
        return new OvertimeCalculation(startLocal, endLocal, hours, crosses);
    }

    public static bool Overlaps(DateTime aStart, DateTime aEnd, DateTime bStart, DateTime bEnd) => aStart < bEnd && bStart < aEnd;
}

/// <summary>Calendario laboral configurable: días hábiles y días festivos.</summary>
public sealed class WorkCalendar
{
    private readonly HashSet<DayOfWeek> _workingDays;
    private readonly Dictionary<DateOnly, string> _holidays;

    public WorkCalendar(IEnumerable<DayOfWeek> workingDays, IEnumerable<(DateOnly Date, string Name)> holidays)
    {
        _workingDays = [.. workingDays];
        _holidays = holidays.GroupBy(h => h.Date).ToDictionary(g => g.Key, g => g.First().Name);
    }

    /// <summary>Lunes a viernes, sin festivos.</summary>
    public static WorkCalendar Default => new([DayOfWeek.Monday, DayOfWeek.Tuesday, DayOfWeek.Wednesday, DayOfWeek.Thursday, DayOfWeek.Friday], []);

    /// <summary>Convierte "1,2,3,4,5" (1 = lunes … 7 = domingo) a días de la semana.</summary>
    public static IReadOnlyList<DayOfWeek> ParseWorkingDays(string csv) =>
        csv.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(s => int.TryParse(s, out var n) && n is >= 1 and <= 7 ? (DayOfWeek)(n % 7) : (DayOfWeek?)null)
            .Where(d => d.HasValue).Select(d => d!.Value).Distinct().ToList();

    public bool IsHoliday(DateOnly date) => _holidays.ContainsKey(date);
    public bool IsWorkingDay(DateOnly date) => _workingDays.Contains(date.DayOfWeek) && !IsHoliday(date);

    public int CountWorkingDays(DateOnly start, DateOnly end)
    {
        if (end < start) return 0;
        var count = 0;
        for (var d = start; d <= end; d = d.AddDays(1))
            if (IsWorkingDay(d)) count++;
        return count;
    }

    public IReadOnlyList<string> HolidaysBetween(DateOnly start, DateOnly end) =>
        _holidays.Where(h => h.Key >= start && h.Key <= end).OrderBy(h => h.Key)
            .Select(h => $"{h.Key.ToString("dd/MM/yyyy", CultureInfo.InvariantCulture)} · {h.Value}").ToList();
}

/// <summary>
/// Tabla de días de vacaciones por antigüedad (referencia: Ley Federal del Trabajo, reforma 2023).
/// Es un valor sugerido y configurable; el saldo oficial lo administra Producto en coordinación con RH.
/// </summary>
public static class VacationEntitlementPolicy
{
    public static int DaysForYearsOfService(int completedYears)
    {
        if (completedYears < 1) return 12; // primer año (se otorga al cumplirlo; se usa como referencia)
        if (completedYears <= 5) return 12 + (completedYears - 1) * 2; // 12,14,16,18,20
        return 20 + ((completedYears - 6) / 5 + 1) * 2; // 6-10:22, 11-15:24, ...
    }

    public static int CompletedYears(DateOnly hireDate, DateOnly asOf)
    {
        var years = asOf.Year - hireDate.Year;
        if (asOf < hireDate.AddYears(years)) years--;
        return Math.Max(0, years);
    }
}

public static class FolioFormatter
{
    public const string Prefix = "TF";
    public static string Format(int year, int sequence) => $"{Prefix}-{year}-{sequence:D6}";

    public static bool IsValid(string folio) =>
        folio.Length == 14 && folio.StartsWith(Prefix + "-", StringComparison.Ordinal)
        && int.TryParse(folio.AsSpan(3, 4), out _) && folio[7] == '-' && int.TryParse(folio.AsSpan(8, 6), out _);
}

/// <summary>
/// Hash canónico del contenido sustantivo de una solicitud. Si cambia cualquier dato relevante,
/// cambia el hash y las firmas anteriores dejan de corresponder a la versión vigente.
/// </summary>
public static class RequestContentHasher
{
    public static string Compute(Request request)
    {
        var p = request.PrimaryPeriod;
        var sb = new StringBuilder();
        void Add(string key, object? value) => sb.Append(key).Append('=').Append(Convert.ToString(value, CultureInfo.InvariantCulture) ?? "").Append('\n');
        Add("id", request.Id);
        Add("folio", request.Folio);
        Add("employee", request.EmployeeId);
        Add("kind", (int)request.Kind);
        Add("version", request.Version);
        Add("start", p?.StartDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
        Add("end", p?.EndDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
        Add("startTime", p?.StartTime?.ToString("HH:mm", CultureInfo.InvariantCulture));
        Add("endTime", p?.EndTime?.ToString("HH:mm", CultureInfo.InvariantCulture));
        Add("fullDay", request.IsFullDay);
        Add("hours", request.TotalHours.ToString("0.00", CultureInfo.InvariantCulture));
        Add("days", request.TotalDays.ToString("0.00", CultureInfo.InvariantCulture));
        Add("reason", request.Reason.Trim());
        Add("justification", request.Justification?.Trim());
        Add("category", request.LeaveCategoryId);
        Add("project", request.Overtime?.Project?.Trim());
        Add("activity", request.Overtime?.Activity?.Trim());
        foreach (var a in request.Attachments.Where(a => !a.IsDeleted).OrderBy(a => a.Sha256, StringComparer.Ordinal))
            Add("attachment", a.Sha256);
        return Sha256Hex(sb.ToString());
    }

    public static string Sha256Hex(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    public static string Sha256Hex(byte[] value) => Convert.ToHexStringLower(SHA256.HashData(value));
}

public static class SignatureHasher
{
    public static string Compute(byte[] imagePng, string documentHash, int signerEmployeeId, Guid requestId, int version, DateTime signedAtUtc)
    {
        var imageHash = RequestContentHasher.Sha256Hex(imagePng);
        return RequestContentHasher.Sha256Hex(string.Join('|', imageHash, documentHash, signerEmployeeId.ToString(CultureInfo.InvariantCulture),
            requestId.ToString("N"), version.ToString(CultureInfo.InvariantCulture), DateTime.SpecifyKind(signedAtUtc, DateTimeKind.Utc).ToString("O", CultureInfo.InvariantCulture)));
    }
}

public static class AuditHasher
{
    public static string Compute(AuditLog entry) => RequestContentHasher.Sha256Hex(string.Join('|',
        entry.PreviousHash,
        entry.Sequence.ToString(CultureInfo.InvariantCulture),
        DateTime.SpecifyKind(entry.OccurredAtUtc, DateTimeKind.Utc).ToString("O", CultureInfo.InvariantCulture),
        entry.ActorEmployeeId?.ToString(CultureInfo.InvariantCulture) ?? "",
        entry.ActorName, entry.Action, entry.EntityType, entry.EntityId, entry.Details ?? "", entry.IpAddress ?? ""));
}
