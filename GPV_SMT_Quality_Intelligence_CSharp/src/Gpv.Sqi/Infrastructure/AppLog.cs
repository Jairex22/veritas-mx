using System.Text.RegularExpressions;

namespace Gpv.Sqi.Infrastructure;

/// <summary>Logs diarios logs/app_YYYY-MM-DD.log con sanitización de secretos.</summary>
public static partial class AppLog
{
    private static readonly object Gate = new();
    private static string? _dir;
    public static bool Console { get; set; } = true;

    private static readonly (Regex Pattern, string Replacement)[] Patterns =
    [
        (new Regex(@"(Authorization\s*[:=]\s*)(Basic|Bearer)\s+[A-Za-z0-9+/=._-]+", RegexOptions.IgnoreCase), "$1$2 ***"),
        (new Regex(@"(password\s*[:=]\s*)\S+", RegexOptions.IgnoreCase), "$1***"),
        (new Regex(@"(GPV_ODATA_PASSWORD\s*=\s*)\S+", RegexOptions.IgnoreCase), "$1***"),
        (new Regex(@"(https?://)[^/\s:@]+:[^/\s@]+@"), "$1***:***@"),
    ];

    public static void Init(string directory)
    {
        Directory.CreateDirectory(directory);
        _dir = directory;
    }

    public static string? Directory_ => _dir;

    public static string Sanitize(string text)
    {
        foreach (var (p, r) in Patterns) text = p.Replace(text, r);
        return text;
    }

    public static void Info(string category, string message) => Write("INFO", category, message);
    public static void Warn(string category, string message) => Write("WARNING", category, message);
    public static void Error(string category, string message, Exception? ex = null) =>
        Write("ERROR", category, ex is null ? message : $"{message} | {ex.GetType().Name}: {ex.Message}\n{ex.StackTrace}");

    /// <summary>Observadores (pruebas) que reciben la línea ya sanitizada.</summary>
    public static event Action<string>? LineWritten;

    private static void Write(string level, string category, string message)
    {
        var now = DateTime.Now;
        var line = $"{now:yyyy-MM-dd HH:mm:ss} | {level} | gpv.{category} | {Sanitize(message)}";
        lock (Gate)
        {
            if (_dir is not null)
            {
                try { File.AppendAllText(Path.Combine(_dir, $"app_{now:yyyy-MM-dd}.log"), line + Environment.NewLine); }
                catch (IOException) { /* el log nunca debe romper la aplicación */ }
            }
            if (Console) System.Console.WriteLine(line);
        }
        LineWritten?.Invoke(line);
    }
}
