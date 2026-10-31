using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>
/// Proveedor del <see cref="TimeFlowApiClient"/> (contrato compartido con la API).
/// Mantiene un único <see cref="HttpClient"/> con BaseAddress = <see cref="ServerSettings.BaseUri"/> y lo reconstruye
/// cuando el usuario cambia el servidor (HttpClient no permite modificar BaseAddress después de usarse).
/// Las páginas deben leer <see cref="Client"/> en cada llamada en lugar de guardarlo.
/// </summary>
public sealed class TimeFlowApi : IDisposable
{
    private static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(30);

    private readonly ServerSettings _settings;
    private readonly Lock _gate = new();
    private HttpClient _http;
    private TimeFlowApiClient _client;
    private string? _token;

    public TimeFlowApi(ServerSettings settings)
    {
        _settings = settings;
        (_http, _client) = Build(settings.BaseUri, null);
        _settings.Changed += OnServerChanged;
    }

    public TimeFlowApiClient Client
    {
        get { lock (_gate) return _client; }
    }

    public Uri BaseAddress => _settings.BaseUri;

    /// <summary>Token JWT vigente (o null). Se usa también para el hub de SignalR.</summary>
    public string? AccessToken
    {
        get { lock (_gate) return _token; }
    }

    public void SetToken(string? token)
    {
        lock (_gate)
        {
            _token = token;
            _client.SetToken(token);
        }
    }

    private void OnServerChanged()
    {
        HttpClient old;
        lock (_gate)
        {
            old = _http;
            (_http, _client) = Build(_settings.BaseUri, _token);
        }
        old.Dispose();
    }

    private static (HttpClient, TimeFlowApiClient) Build(Uri baseUri, string? token)
    {
        // Sin handler explícito: en Android/iOS se usa el handler nativo de la plataforma (respeta la política de red).
        var http = new HttpClient { BaseAddress = baseUri, Timeout = RequestTimeout };
        http.DefaultRequestHeaders.AcceptLanguage.ParseAdd("es-MX");
        var client = new TimeFlowApiClient(http);
        client.SetToken(token);
        return (http, client);
    }

    public void Dispose()
    {
        _settings.Changed -= OnServerChanged;
        _http.Dispose();
    }
}
