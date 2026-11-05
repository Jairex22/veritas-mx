using System.Globalization;
using System.Text.RegularExpressions;

namespace Gpv.Sqi.Infrastructure;

/// <summary>Fecha OData parseada. HasOffset=false equivale a fecha "naive" (no verificable).</summary>
public readonly record struct ParsedTime(DateTimeOffset Value, bool HasOffset);

public static partial class TimeParse
{
    [GeneratedRegex(@"^/Date\((-?\d+)([+-]\d{4})?\)/$")]
    private static partial Regex V2Date();

    [GeneratedRegex(@"(Z|[+-]\d{2}:?\d{2})$")]
    private static partial Regex OffsetSuffix();

    [GeneratedRegex(@"(\.\d{7})\d+")]
    private static partial Regex LongFraction();

    public static ParsedTime? Parse(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) return null;
        var m = V2Date().Match(value);
        if (m.Success)
        {
            var dt = DateTimeOffset.FromUnixTimeMilliseconds(long.Parse(m.Groups[1].Value, CultureInfo.InvariantCulture));
            if (m.Groups[2].Success)
            {
                var g = m.Groups[2].Value;
                var off = new TimeSpan(int.Parse(g[1..3], CultureInfo.InvariantCulture), int.Parse(g[3..5], CultureInfo.InvariantCulture), 0);
                dt = dt.ToOffset(g[0] == '-' ? -off : off);
            }
            return new ParsedTime(dt, true);
        }
        var s = LongFraction().Replace(value.Trim(), "$1");
        var hasOffset = OffsetSuffix().IsMatch(s);
        var styles = hasOffset ? DateTimeStyles.None : DateTimeStyles.AssumeUniversal;
        if (!DateTimeOffset.TryParse(s, CultureInfo.InvariantCulture, styles, out var parsed)) return null;
        if (!s.Contains('T') && !s.Contains(' ')) return null;
        return new ParsedTime(parsed, hasOffset);
    }

    /// <summary>Clave de orden: fechas sin zona y ausentes al final.</summary>
    public static (int, long) SortKey(ParsedTime? t) => t is null
        ? (2, 0)
        : t.Value.HasOffset ? (0, t.Value.Value.UtcTicks) : (1, t.Value.Value.UtcTicks);

    public static (int, long) SortKey(string? value) => SortKey(Parse(value));

    public static TimeSpan ParseOffset(string? text)
    {
        var m = Regex.Match(text ?? "", @"^([+-])(\d{2}):(\d{2})$");
        if (!m.Success) return TimeSpan.Zero;
        var ts = new TimeSpan(int.Parse(m.Groups[2].Value, CultureInfo.InvariantCulture), int.Parse(m.Groups[3].Value, CultureInfo.InvariantCulture), 0);
        return m.Groups[1].Value == "-" ? -ts : ts;
    }

    /// <summary>ISO-8601 con offset (equivalente a datetime.isoformat de Python).</summary>
    public static string Iso(DateTimeOffset d, bool millis = false)
    {
        var fmt = millis ? "yyyy-MM-dd'T'HH:mm:ss.fff" : "yyyy-MM-dd'T'HH:mm:ss";
        var off = d.Offset;
        var sign = off < TimeSpan.Zero ? "-" : "+";
        off = off.Duration();
        return d.ToString(fmt, CultureInfo.InvariantCulture) + $"{sign}{off.Hours:00}:{off.Minutes:00}";
    }

    public static string NowUtcIso() => Iso(DateTimeOffset.UtcNow);
}
