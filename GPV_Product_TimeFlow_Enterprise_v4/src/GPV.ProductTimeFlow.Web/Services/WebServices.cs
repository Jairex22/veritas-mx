using System.Collections.Concurrent;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure.Hosting;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Components.Authorization;

namespace GPV.ProductTimeFlow.Web.Services;

/// <summary>
/// Identidad del circuito Blazor. La IP y el agente de usuario se capturan en la petición inicial
/// (App.razor) y se pasan al circuito, porque HttpContext no está disponible en modo interactivo.
/// </summary>
public sealed class UserSession(AuthenticationStateProvider auth)
{
    private Actor? _actor;
    public string? ClientIp { get; set; }
    public string? UserAgent { get; set; }
    public UserProfileDto? Profile { get; set; }

    public async Task<Actor> GetActorAsync()
    {
        if (_actor is not null) return _actor;
        var state = await auth.GetAuthenticationStateAsync();
        var actor = ActorFactory.FromPrincipal(state.User) ?? throw new ForbiddenException("Sesión no válida.");
        _actor = actor with { IpAddress = ClientIp, UserAgent = UserAgent };
        return _actor;
    }

    public bool Has(UserRole role) => _actor?.Has(role) ?? false;
}

/// <summary>
/// Ejecuta cada operación en su propio ámbito de DI (DbContext independiente). En Blazor Server el ámbito
/// del circuito vive mucho tiempo y puede recibir operaciones concurrentes; este patrón evita compartir el DbContext.
/// </summary>
public sealed class ServiceRunner(IServiceScopeFactory scopes, UserSession session)
{
    public async Task<T> Run<TService, T>(Func<TService, Actor, Task<T>> work) where TService : notnull
    {
        var actor = await session.GetActorAsync();
        await using var scope = scopes.CreateAsyncScope();
        return await work(scope.ServiceProvider.GetRequiredService<TService>(), actor);
    }

    public async Task Run<TService>(Func<TService, Actor, Task> work) where TService : notnull
    {
        var actor = await session.GetActorAsync();
        await using var scope = scopes.CreateAsyncScope();
        await work(scope.ServiceProvider.GetRequiredService<TService>(), actor);
    }
}

public enum ToastKind { Success, Error, Info, Warning }
public sealed record Toast(Guid Id, ToastKind Kind, string Title, string? Message);

public sealed class ToastService
{
    public event Action? Changed;
    private readonly List<Toast> _items = [];
    public IReadOnlyList<Toast> Items => _items;

    public void Show(ToastKind kind, string title, string? message = null)
    {
        var toast = new Toast(Guid.NewGuid(), kind, title, message);
        _items.Add(toast);
        Changed?.Invoke();
        _ = Task.Delay(kind == ToastKind.Error ? 9000 : 5000).ContinueWith(_ => Dismiss(toast.Id));
    }

    public void Success(string title, string? message = null) => Show(ToastKind.Success, title, message);
    public void Info(string title, string? message = null) => Show(ToastKind.Info, title, message);

    public void Error(Exception ex)
    {
        var (title, message) = ex switch
        {
            BusinessRuleException b => ("Revise la información", string.Join(" ", b.Errors)),
            ConflictException c => ("No se pudo completar", c.Message),
            Domain.InvalidTransitionException t => ("Acción no válida", t.Message),
            NotFoundException n => ("No encontrado", n.Message),
            ForbiddenException f => ("Sin permiso", f.Message),
            _ => ("Ocurrió un error inesperado", "El incidente quedó registrado. Intente de nuevo.")
        };
        Show(ToastKind.Error, title, message);
    }

    public void Dismiss(Guid id)
    {
        lock (_items) _items.RemoveAll(t => t.Id == id);
        Changed?.Invoke();
    }
}

/// <summary>Limitador de intentos de inicio de sesión por IP (complementa el bloqueo por cuenta).</summary>
public sealed class LoginThrottle
{
    private readonly ConcurrentDictionary<string, (int Count, DateTime WindowStart)> _attempts = new();
    public int MaxPerMinute { get; init; } = 20;

    public bool Allow(string? ip)
    {
        var key = ip ?? "unknown";
        var now = DateTime.UtcNow;
        var entry = _attempts.AddOrUpdate(key, _ => (1, now), (_, e) => now - e.WindowStart > TimeSpan.FromMinutes(1) ? (1, now) : (e.Count + 1, e.WindowStart));
        return entry.Count <= MaxPerMinute;
    }
}

public static class Format
{
    private static readonly System.Globalization.CultureInfo Es = System.Globalization.CultureInfo.GetCultureInfo("es-MX");
    private static readonly TimeZoneInfo Zone = ResolveZone();

    private static TimeZoneInfo ResolveZone()
    {
        try { return TimeZoneInfo.FindSystemTimeZoneById("America/Mexico_City"); }
        catch (TimeZoneNotFoundException) { return TimeZoneInfo.Local; }
    }

    public static System.DateTime Local(System.DateTime utc) => TimeZoneInfo.ConvertTimeFromUtc(System.DateTime.SpecifyKind(utc, DateTimeKind.Utc), Zone);
    public static string DateTime(System.DateTime? utc) => utc is null ? "—" : Local(utc.Value).ToString("dd MMM yyyy, HH:mm", Es);
    public static string Date(DateOnly d) => d.ToString("dd MMM yyyy", Es);
    public static string DateLong(DateOnly d) => d.ToString("dddd d 'de' MMMM", Es);
    public static string Relative(System.DateTime utc)
    {
        var diff = System.DateTime.UtcNow - DateTime_SpecifyUtc(utc);
        if (diff.TotalMinutes < 1) return "hace un momento";
        if (diff.TotalMinutes < 60) return $"hace {(int)diff.TotalMinutes} min";
        if (diff.TotalHours < 24) return $"hace {(int)diff.TotalHours} h";
        if (diff.TotalDays < 7) return $"hace {(int)diff.TotalDays} d";
        return Local(utc).ToString("dd MMM", Es);
    }
    private static System.DateTime DateTime_SpecifyUtc(System.DateTime d) => System.DateTime.SpecifyKind(d, DateTimeKind.Utc);

    public static string Period(RequestSummaryDto s)
    {
        if (s.Kind == RequestKind.Overtime || !s.IsFullDay)
            return $"{Date(s.StartDate)} · {s.StartTime:HH\\:mm}–{s.EndTime:HH\\:mm}";
        return s.StartDate == s.EndDate ? Date(s.StartDate) : $"{s.StartDate.ToString("dd MMM", Es)} – {Date(s.EndDate)}";
    }

    public static string Duration(RequestSummaryDto s) =>
        s.Kind == RequestKind.Overtime || !s.IsFullDay ? Labels.Hours(s.Hours) : Labels.Days(s.Days);

    public static string Month(int year, int month) => new System.DateTime(year, month, 1, 0, 0, 0, DateTimeKind.Unspecified).ToString("MMMM yyyy", Es);
    public static string Bytes(long size) => size < 1024 ? $"{size} B" : size < 1024 * 1024 ? $"{size / 1024.0:0.#} KB" : $"{size / 1024.0 / 1024.0:0.#} MB";
    public static System.Globalization.CultureInfo Culture => Es;
}
