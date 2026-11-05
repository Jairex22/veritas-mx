using System.Collections.Concurrent;
using System.Diagnostics;
using Gpv.Sqi.Models;

namespace Gpv.Sqi.OData;

/// <summary>
/// Protección de FactoryLogix, compartida por todos los clientes de la aplicación (sobrevive a cambios de configuración):
/// - Caché de respuestas: la misma consulta dentro de N segundos no vuelve a FactoryLogix.
/// - Pausa por entidad: tras TIMEOUT / HTTP 5xx / 429 / error de red no se envían más consultas a esa entidad durante N segundos
///   (FactoryLogix puede seguir procesando la consulta anterior aunque la aplicación haya dejado de esperar).
/// - Ritmo mínimo: separación mínima entre solicitudes consecutivas.
/// </summary>
public sealed class ODataGuard
{
    public static readonly HashSet<ODataStatus> TripStatuses =
        [ODataStatus.TIMEOUT, ODataStatus.SERVER_ERROR, ODataStatus.RATE_LIMITED, ODataStatus.CONNECTION_ERROR];

    private const int MaxCacheEntries = 200;
    private readonly ConcurrentDictionary<string, (long Expires, QueryResult Result)> _cache = new();
    private readonly ConcurrentDictionary<string, (long Until, string Reason)> _cooldown = new();
    private readonly SemaphoreSlim _pace = new(1, 1);
    private long _lastRequest;

    private static long Now => Stopwatch.GetTimestamp();
    private static long After(double seconds) => Now + (long)(seconds * Stopwatch.Frequency);

    public QueryResult? TryCache(string key)
    {
        if (!_cache.TryGetValue(key, out var e)) return null;
        if (e.Expires < Now) { _cache.TryRemove(key, out _); return null; }
        return e.Result;
    }

    public void Store(string key, QueryResult result, double seconds)
    {
        if (seconds <= 0 || !result.Ok) return;
        if (_cache.Count >= MaxCacheEntries)
            foreach (var k in _cache.Where(kv => kv.Value.Expires < Now).Select(kv => kv.Key).ToList()) _cache.TryRemove(k, out _);
        if (_cache.Count >= MaxCacheEntries) _cache.Clear();
        _cache[key] = (After(seconds), result);
    }

    /// <summary>Segundos restantes de pausa para la entidad (0 si no hay pausa) y su causa.</summary>
    public (int Remaining, string Reason) Cooldown(string entity)
    {
        if (!_cooldown.TryGetValue(entity, out var c)) return (0, "");
        var left = (c.Until - Now) / (double)Stopwatch.Frequency;
        if (left <= 0) { _cooldown.TryRemove(entity, out _); return (0, ""); }
        return ((int)Math.Ceiling(left), c.Reason);
    }

    public void Trip(string entity, ODataStatus status, double seconds)
    {
        if (seconds > 0 && TripStatuses.Contains(status)) _cooldown[entity] = (After(seconds), status.ToString());
    }

    public void Reset(string entity) => _cooldown.TryRemove(entity, out _);

    /// <summary>Espera hasta que haya pasado el intervalo mínimo desde la solicitud anterior.</summary>
    public async Task PaceAsync(double minIntervalMs, CancellationToken ct)
    {
        if (minIntervalMs <= 0) return;
        await _pace.WaitAsync(ct);
        try
        {
            var waitMs = (_lastRequest + (long)(minIntervalMs / 1000 * Stopwatch.Frequency) - Now) * 1000.0 / Stopwatch.Frequency;
            if (_lastRequest > 0 && waitMs > 0) await Task.Delay(TimeSpan.FromMilliseconds(waitMs), ct);
            _lastRequest = Now;
        }
        finally { _pace.Release(); }
    }

    public Dictionary<string, object?> Snapshot() => new()
    {
        ["cached_responses"] = _cache.Count(kv => kv.Value.Expires >= Now),
        ["paused_entities"] = _cooldown.Keys.Select(e => (Entity: e, C: Cooldown(e))).Where(x => x.C.Remaining > 0)
            .Select(x => new Dictionary<string, object?> { ["entity"] = x.Entity, ["remaining_seconds"] = x.C.Remaining, ["reason"] = x.C.Reason })
            .ToList(),
    };
}
