using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Text;
using Gpv.Sqi.Config;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Models;

namespace Gpv.Sqi.OData;

/// <summary>
/// Cliente FactoryLogix OData:
/// - lista blanca de entidades/campos; tipos y versión leídos de $metadata (respaldo marcado como no verificado);
/// - límite global de solicitudes simultáneas (por defecto 1);
/// - reintentos con backoff solo ante HTTP 429/500/502/503/504; nunca ante 401/403/timeout;
/// - sin redirecciones, sin proxy del sistema, sin cookies;
/// - timeout de conexión y timeout total separados;
/// - validación estricta del JSON; medición de tiempos; nunca registra credenciales.
/// </summary>
public sealed class FactoryLogixODataClient : IDataSource, IDisposable
{
    private const double MetadataRetrySeconds = 300;

    private readonly AppConfig _config;
    private readonly string _baseUrl;
    private readonly Func<AppConfig, Credential?> _credentialProvider;
    private readonly Action<QueryResult>? _onResult;
    private readonly SemaphoreSlim _semaphore;
    private readonly SemaphoreSlim _metadataLock = new(1, 1);
    private readonly HttpClient _http;
    private ODataMetadata? _metadata;
    private long _metadataAt;          // Stopwatch ticks
    private long _metadataFailedAt;

    public Dictionary<string, object?>? LastMetadataStatus { get; private set; }

    public FactoryLogixODataClient(AppConfig config, Func<AppConfig, Credential?>? credentialProvider = null,
                                   Action<QueryResult>? onResult = null)
    {
        _config = config;
        _baseUrl = config.Str("odata.base_url").TrimEnd('/') + "/";
        _credentialProvider = credentialProvider ?? Credentials.Get;
        _onResult = onResult;
        var max = Math.Max(1, config.Int("odata.max_concurrent_requests"));
        _semaphore = new SemaphoreSlim(max, max);
        var connect = config.Node("odata.connect_timeout_seconds") is null ? 5 : config.Num("odata.connect_timeout_seconds");
        _http = new HttpClient(new SocketsHttpHandler
        {
            UseProxy = false,
            AllowAutoRedirect = false,
            UseCookies = false,
            ConnectTimeout = TimeSpan.FromSeconds(Math.Min(connect, config.Num("odata.timeout_seconds"))),
            PooledConnectionLifetime = TimeSpan.FromMinutes(5),
        })
        { Timeout = Timeout.InfiniteTimeSpan };
    }

    public void Dispose() { _http.Dispose(); _semaphore.Dispose(); _metadataLock.Dispose(); }

    // ------------------------------------------------------------------ política
    public QueryResult? PolicyCheck(string entity)
    {
        if (_config.Mode != "live")
            return new QueryResult(ODataStatus.BLOCKED_BY_POLICY, entity) { Error = "La aplicación está en modo demostración" };
        if (!_config.Bool("security.live_mode_approved"))
            return new QueryResult(ODataStatus.BLOCKED_BY_POLICY, entity)
            { Error = "El modo de conexión real no está aprobado (security.live_mode_approved=false en config.json)" };
        var scheme = new Uri(_baseUrl).Scheme;
        if (_config.Str("odata.auth_method") == "basic" && scheme != "https" && !_config.Bool("security.allow_basic_auth_over_http"))
            return new QueryResult(ODataStatus.BLOCKED_BY_POLICY, entity)
            {
                Error = "Basic Auth sobre HTTP no está aprobado por TI. Se requiere HTTPS/proxy corporativo o aprobación explícita (security.allow_basic_auth_over_http).",
            };
        return null;
    }

    private (string? Header, QueryResult? Problem) AuthHeader(string entity)
    {
        if (_config.Str("odata.auth_method") == "none") return (null, null);
        Credential? cred;
        try { cred = _credentialProvider(_config); }
        catch (CredentialException ex) { return (null, new QueryResult(ODataStatus.NOT_CONFIGURED, entity) { Error = ex.Message }); }
        if (cred is null) return (null, new QueryResult(ODataStatus.NOT_CONFIGURED, entity) { Error = "No hay credenciales configuradas para FactoryLogix" });
        return ("Basic " + Convert.ToBase64String(Encoding.UTF8.GetBytes($"{cred.Username}:{cred.Password}")), null);
    }

    // ------------------------------------------------------------------ HTTP
    private bool SameOrigin(string url)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var a)) return false;
        var b = new Uri(_baseUrl);
        return a.Scheme == b.Scheme && a.Host.Equals(b.Host, StringComparison.OrdinalIgnoreCase) && a.Port == b.Port;
    }

    private static double Ms(long ticks) => ticks * 1000.0 / Stopwatch.Frequency;

    /// <summary>Una solicitud con reintentos acotados. Devuelve (resultado, cuerpo).</summary>
    private async Task<(QueryResult Result, byte[]? Body)> RequestAsync(string url, string entity, string accept, string description, CancellationToken ct)
    {
        var result = new QueryResult(ODataStatus.CONNECTION_ERROR, entity) { QueryDescription = description, DataSource = "live" };
        var (auth, problem) = AuthHeader(entity);
        if (problem is not null) { problem.QueryDescription = description; return (problem, null); }

        var timeout = _config.Num("odata.timeout_seconds");
        var maxBytes = (long)(_config.Num("odata.max_response_mb") * 1024 * 1024);
        var maxAttempts = 1 + Math.Clamp(_config.Int("odata.max_retries"), 0, 2);
        var backoff = _config.Num("odata.backoff_seconds");
        var timings = new Dictionary<string, double> { ["wait_headers_ms"] = 0, ["download_ms"] = 0, ["backoff_ms"] = 0 };
        var started = Stopwatch.GetTimestamp();
        byte[]? body = null;

        for (var attempt = 1; attempt <= maxAttempts; attempt++)
        {
            result.Attempts = attempt;
            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            req.Headers.Accept.ParseAdd(accept);
            req.Headers.UserAgent.ParseAdd("GPV-SMT-Quality-Intelligence");
            if (auth is not null) req.Headers.Authorization = AuthenticationHeaderValue.Parse(auth);

            using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            cts.CancelAfter(TimeSpan.FromSeconds(timeout));
            var t0 = Stopwatch.GetTimestamp();
            TimeSpan? retryAfter = null;
            var headersDone = false;
            try
            {
                using var resp = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, cts.Token);
                var t1 = Stopwatch.GetTimestamp();
                headersDone = true;
                timings["wait_headers_ms"] += Ms(t1 - t0);
                var code = (int)resp.StatusCode;
                result.HttpStatus = code;
                if (code is >= 200 and < 300)
                {
                    await using var stream = await resp.Content.ReadAsStreamAsync(cts.Token);
                    using var buffer = new MemoryStream();
                    var chunk = new byte[81920];
                    int n;
                    var tooLarge = false;
                    while ((n = await stream.ReadAsync(chunk, cts.Token)) > 0)
                    {
                        buffer.Write(chunk, 0, n);
                        if (buffer.Length > maxBytes) { tooLarge = true; break; }
                    }
                    timings["download_ms"] += Ms(Stopwatch.GetTimestamp() - t1);
                    if (tooLarge) { result.Status = ODataStatus.INVALID_RESPONSE; result.Error = "La respuesta excede el tamaño máximo permitido"; }
                    else { result.Status = ODataStatus.OK; result.Error = null; body = buffer.ToArray(); }
                    break;
                }
                (result.Status, result.Error) = MapHttp(code, resp.ReasonPhrase);
                if (ODataStatusInfo.RetryableHttp.Contains(code) && attempt < maxAttempts)
                    retryAfter = resp.Headers.RetryAfter?.Delta;
                else
                    break;
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                timings[headersDone ? "download_ms" : "wait_headers_ms"] += Ms(Stopwatch.GetTimestamp() - t0);
                result.Status = ODataStatus.TIMEOUT;
                result.Error = $"Sin respuesta completa en {Json.Num(timeout)} s";
                break;   // un timeout no se reintenta: evita cargar más al servidor
            }
            catch (HttpRequestException ex)
            {
                timings["wait_headers_ms"] += Ms(Stopwatch.GetTimestamp() - t0);
                result.Status = ODataStatus.CONNECTION_ERROR;
                var socket = ex.InnerException as SocketException;
                result.Error = ex.HttpRequestError switch
                {
                    HttpRequestError.NameResolutionError => "No se pudo resolver el nombre del servidor (DNS)",
                    _ when socket?.SocketErrorCode is SocketError.HostNotFound or SocketError.NoData or SocketError.TryAgain
                        => "No se pudo resolver el nombre del servidor (DNS)",
                    _ when socket?.SocketErrorCode == SocketError.ConnectionRefused => "Conexión rechazada por el servidor",
                    _ when socket?.SocketErrorCode == SocketError.TimedOut => "Tiempo de conexión agotado",
                    _ => $"Servidor inaccesible: {ex.HttpRequestError}",
                };
                if (socket?.SocketErrorCode == SocketError.TimedOut) result.Status = ODataStatus.TIMEOUT;
                break;
            }
            catch (IOException ex)
            {
                timings["download_ms"] += Ms(Stopwatch.GetTimestamp() - t0);
                result.Status = ODataStatus.CONNECTION_ERROR;
                result.Error = $"Conexión interrumpida: {ex.GetType().Name}";
                break;
            }

            var wait = backoff * attempt;
            if (retryAfter is { } ra) wait = Math.Min(30.0, Math.Max(wait, ra.TotalSeconds));
            AppLog.Warn("odata", $"Reintento {attempt + 1}/{maxAttempts} para {entity} tras {result.Status} (espera {wait:0.0}s)");
            await Task.Delay(TimeSpan.FromSeconds(wait), ct);
            timings["backoff_ms"] += wait * 1000;
        }
        result.ElapsedMs = Ms(Stopwatch.GetTimestamp() - started);
        result.Timings = timings;
        result.FetchedAt = TimeParse.NowUtcIso();
        return (result, body);
    }

    public static (ODataStatus, string) MapHttp(int code, string? reason) => code switch
    {
        401 => (ODataStatus.AUTH_ERROR, "HTTP 401: credenciales rechazadas o ausentes"),
        403 => (ODataStatus.FORBIDDEN, "HTTP 403: el usuario no tiene permiso para esta entidad"),
        404 => (ODataStatus.NOT_FOUND, "HTTP 404: entidad o endpoint inexistente"),
        400 => (ODataStatus.BAD_REQUEST, "HTTP 400: el servidor rechazó la consulta"),
        429 => (ODataStatus.RATE_LIMITED, "HTTP 429: demasiadas solicitudes"),
        >= 500 and <= 599 => (ODataStatus.SERVER_ERROR, $"HTTP {code}: error del servidor FactoryLogix"),
        >= 300 and <= 399 => (ODataStatus.HTTP_ERROR, $"HTTP {code}: redirección no permitida"),
        _ => (ODataStatus.HTTP_ERROR, $"HTTP {code}: {reason}"),
    };

    private QueryResult Emit(QueryResult r)
    {
        AppLog.Info("odata", $"ODATA | {r.Entity} | {r.Status} | HTTP={r.HttpStatus?.ToString() ?? "None"} | {r.ElapsedMs:0} ms | intentos={r.Attempts} | filas={r.Rows.Count} | {r.QueryDescription} | {r.Error}");
        try { _onResult?.Invoke(r); }
        catch (Exception ex) { AppLog.Error("odata", "Error registrando auditoría de consulta", ex); }
        return r;
    }

    private async Task<QueryResult?> AcquireAsync(string entity, CancellationToken ct)
    {
        var wait = TimeSpan.FromSeconds(_config.Num("odata.timeout_seconds") * 2);
        return await _semaphore.WaitAsync(wait, ct) ? null
            : new QueryResult(ODataStatus.BUSY, entity) { Error = "Límite de solicitudes simultáneas alcanzado; intente de nuevo" };
    }

    // ------------------------------------------------------------------ metadata
    public async Task<(QueryResult Result, ODataMetadata? Metadata)> FetchMetadataAsync(CancellationToken ct = default)
    {
        var blocked = PolicyCheck("$metadata");
        if (blocked is not null) return (Emit(blocked), null);
        var busy = await AcquireAsync("$metadata", ct);
        if (busy is not null) return (Emit(busy), null);
        QueryResult result; byte[]? body;
        try { (result, body) = await RequestAsync(_baseUrl + "$metadata", "$metadata", "application/xml", "$metadata", ct); }
        finally { _semaphore.Release(); }
        ODataMetadata? meta = null;
        if (result.Status == ODataStatus.OK && body is not null)
        {
            try { meta = MetadataParser.Parse(body); }
            catch (MetadataException ex) { result.Status = ODataStatus.INVALID_RESPONSE; result.Error = ex.Message; }
        }
        await _metadataLock.WaitAsync(ct);
        try
        {
            if (meta is not null) { _metadata = meta; _metadataAt = Stopwatch.GetTimestamp(); }
            else _metadataFailedAt = Stopwatch.GetTimestamp();
            LastMetadataStatus = result.ToStatusDict();
        }
        finally { _metadataLock.Release(); }
        return (Emit(result), meta);
    }

    private async Task<ODataMetadata?> MetadataAsync(CancellationToken ct)
    {
        var ttl = _config.Num("odata.metadata_ttl_minutes") * 60;
        var now = Stopwatch.GetTimestamp();
        if (_metadata is not null && Ms(now - _metadataAt) / 1000 < ttl) return _metadata;
        if (_metadataFailedAt > 0 && Ms(now - _metadataFailedAt) / 1000 < MetadataRetrySeconds) return _metadata;
        var (_, meta) = await FetchMetadataAsync(ct);
        return meta ?? _metadata;
    }

    // ------------------------------------------------------------------ consulta
    public async Task<QueryResult> ExecuteAsync(QuerySpec spec, CancellationToken ct = default)
    {
        var description = spec.Describe();
        var blocked = PolicyCheck(spec.Entity);
        if (blocked is not null) { blocked.QueryDescription = description; return Emit(blocked); }
        var meta = await MetadataAsync(ct);
        IReadOnlyDictionary<string, PropertyInfo>? props = Entities.Known.GetValueOrDefault(spec.Entity);
        var version = "4";
        var verified = false;
        if (meta is not null)
        {
            var real = meta.PropertiesFor(spec.Entity);
            if (real is null)
                return Emit(new QueryResult(ODataStatus.NOT_FOUND, spec.Entity)
                { QueryDescription = description, Error = $"La entidad {spec.Entity} no existe en $metadata" });
            props = real; version = meta.OdataVersion; verified = true;
        }
        string url;
        try { url = ODataFilterBuilder.BuildQueryUrl(_baseUrl, spec, props, version); }
        catch (FilterException ex)
        {
            return Emit(new QueryResult(ODataStatus.VALIDATION_ERROR, spec.Entity) { QueryDescription = description, Error = ex.Message });
        }
        if (!verified) description += " | tipos no verificados ($metadata no disponible)";

        var busy = await AcquireAsync(spec.Entity, ct);
        if (busy is not null) { busy.QueryDescription = description; return Emit(busy); }
        try
        {
            var all = new List<JsonObjectRow>();
            var total = new QueryResult(ODataStatus.OK, spec.Entity) { QueryDescription = description, DataSource = "live" };
            var pages = 0;
            string? nextUrl = url;
            var maxPages = _config.Int("odata.max_pages");
            var exhausted = true;
            while (nextUrl is not null)
            {
                if (pages >= maxPages) { exhausted = false; break; }
                pages++;
                var (res, body) = await RequestAsync(nextUrl, spec.Entity, "application/json", description, ct);
                total.Attempts += res.Attempts;
                total.ElapsedMs += res.ElapsedMs;
                foreach (var (k, v) in res.Timings) total.Timings[k] = total.Timings.GetValueOrDefault(k) + v;
                total.HttpStatus = res.HttpStatus;
                total.FetchedAt = res.FetchedAt;
                if (res.Status != ODataStatus.OK || body is null)
                {
                    total.Status = res.Status; total.Error = res.Error; total.Rows = [];
                    return Emit(total);
                }
                var tp = Stopwatch.GetTimestamp();
                List<System.Text.Json.Nodes.JsonObject> rows; string? nextLink;
                try { (rows, nextLink) = ODataPayloadParser.Parse(body); }
                catch (PayloadException ex)
                {
                    total.Status = ODataStatus.INVALID_RESPONSE; total.Error = ex.Message; total.Rows = [];
                    return Emit(total);
                }
                total.Timings["parse_ms"] = total.Timings.GetValueOrDefault("parse_ms") + Ms(Stopwatch.GetTimestamp() - tp);
                all.AddRange(rows.Select(r => new JsonObjectRow(r)));
                if (all.Count >= spec.Top)
                {
                    all = all.Take(spec.Top).ToList();
                    total.Truncated = nextLink is not null || rows.Count >= spec.Top;
                    break;
                }
                if (nextLink is not null && !SameOrigin(nextLink))
                {
                    total.Error = "nextLink de otro origen ignorado";
                    total.Truncated = true;
                    break;
                }
                nextUrl = nextLink;
            }
            if (!exhausted) total.Truncated = true;
            if (all.Count >= spec.Top) total.Truncated = true;
            total.Rows = all.Select(r => r.Row).ToList();
            total.Status = total.Rows.Count > 0 ? ODataStatus.OK : ODataStatus.EMPTY;
            return Emit(total);
        }
        finally { _semaphore.Release(); }
    }

    private readonly record struct JsonObjectRow(System.Text.Json.Nodes.JsonObject Row);
}
