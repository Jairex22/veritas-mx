using System.Text.Json.Nodes;
using Gpv.Sqi.Api;
using Gpv.Sqi.Config;
using Gpv.Sqi.Infrastructure;

namespace Gpv.Sqi.Services;

/// <summary>Ventanas temporales (últimos N minutos, turno actual, personalizado).</summary>
public static class TimeWindows
{
    public static readonly Dictionary<string, int> Presets = new() { ["5m"] = 5, ["15m"] = 15, ["1h"] = 60, ["4h"] = 240, ["24h"] = 1440 };
    public const int MaxCustomHours = 24 * 7;

    public static (string Name, DateTimeOffset Start)? CurrentShift(JsonArray? shifts, string offset, DateTimeOffset? now = null)
    {
        var tz = TimeParse.ParseOffset(offset);
        var local = (now ?? DateTimeOffset.UtcNow).ToOffset(tz);
        foreach (var sh in shifts ?? [])
        {
            if (sh is not JsonObject o) continue;
            if (!TimeOnly.TryParse(o.Str("start"), out var start) || !TimeOnly.TryParse(o.Str("end"), out var end)) continue;
            var name = o.Str("name") ?? "Turno";
            var todayStart = new DateTimeOffset(local.Year, local.Month, local.Day, start.Hour, start.Minute, 0, tz);
            var t = TimeOnly.FromTimeSpan(local.TimeOfDay);
            if (start < end) { if (t >= start && t < end) return (name, todayStart); }
            else
            {
                if (t >= start) return (name, todayStart);
                if (t < end) return (name, todayStart.AddDays(-1));
            }
        }
        return null;
    }

    public static (DateTimeOffset Start, DateTimeOffset End, string Label) Resolve(JsonObject p, AppConfig cfg, DateTimeOffset? now = null)
    {
        var n = now ?? DateTimeOffset.UtcNow;
        var window = InputValidation.GetString(p, "window") ?? "15m";
        if (Presets.TryGetValue(window, out var minutes)) return (n.AddMinutes(-minutes), n, window);
        if (window == "shift")
        {
            var found = CurrentShift(cfg.Node("pulse.shifts") as JsonArray, cfg.Str("app.display_utc_offset"), n)
                        ?? throw new InputException("No hay turnos configurados que incluyan la hora actual");
            return (found.Start.ToUniversalTime(), n, $"turno: {found.Name}");
        }
        if (window == "custom")
        {
            var start = InputValidation.ClientDateTime(InputValidation.GetString(p, "from"), "Desde").ToUniversalTime();
            var end = InputValidation.ClientDateTime(InputValidation.GetString(p, "to"), "Hasta").ToUniversalTime();
            if (end <= start) throw new InputException("La fecha final debe ser posterior a la inicial");
            if (end - start > TimeSpan.FromHours(MaxCustomHours)) throw new InputException("El periodo personalizado no puede exceder 7 días");
            return (start, end, "personalizado");
        }
        throw new InputException("Ventana de tiempo no válida");
    }

    public static Dictionary<string, object?> Describe(DateTimeOffset start, DateTimeOffset end, string label, AppConfig cfg)
    {
        var tz = TimeParse.ParseOffset(cfg.Str("app.display_utc_offset"));
        return new() { ["label"] = label, ["start"] = TimeParse.Iso(start.ToOffset(tz)), ["end"] = TimeParse.Iso(end.ToOffset(tz)) };
    }
}
