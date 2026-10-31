using System.Net;
using System.Text.Json.Serialization;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.SignalR.Client;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>
/// Contador de notificaciones no leídas y avisos en tiempo real.
/// - SignalR: hub /hubs/notifications (token por AccessTokenProvider → ?access_token=), evento "notification" con <see cref="NotificationDto"/>.
/// - Respaldo: consulta UnreadCountAsync cada 60 s (y reintenta conectar el hub si se cayó).
/// Se activa/desactiva solo al iniciar/cerrar sesión (<see cref="AuthState.Changed"/>).
/// </summary>
public sealed class NotificationCenter : IAsyncDisposable
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromSeconds(60);

    private readonly TimeFlowApi _api;
    private readonly AuthState _auth;
    private readonly ServerSettings _settings;
    private readonly ILogger<NotificationCenter> _logger;
    private readonly SemaphoreSlim _lifecycle = new(1, 1);

    private HubConnection? _hub;
    private CancellationTokenSource? _cts;
    private Task? _pollLoop;
    private int? _sessionEmployeeId;
    private Uri? _hubUri;

    public NotificationCenter(TimeFlowApi api, AuthState auth, ServerSettings settings, ILogger<NotificationCenter> logger)
    {
        _api = api;
        _auth = auth;
        _settings = settings;
        _logger = logger;
        _auth.Changed += OnAuthChanged;
        _settings.Changed += OnAuthChanged;
    }

    public int UnreadCount { get; private set; }

    /// <summary>Estado del canal en tiempo real (para mostrarlo en Ajustes).</summary>
    public bool IsRealtimeConnected => _hub?.State == HubConnectionState.Connected;

    /// <summary>Cambió el contador de no leídas o el estado de conexión.</summary>
    public event Action? Changed;

    /// <summary>Llegó una notificación en tiempo real.</summary>
    public event Action<NotificationDto>? Received;

    private void OnAuthChanged() => _ = SyncWithSessionAsync();

    /// <summary>Arranca o detiene los canales según el estado de la sesión.</summary>
    public async Task SyncWithSessionAsync()
    {
        await _lifecycle.WaitAsync();
        try
        {
            var employeeId = _auth.IsAuthenticated ? _auth.Profile!.EmployeeId : (int?)null;
            // Misma sesión contra el mismo servidor: nada que hacer.
            if (employeeId is not null && employeeId == _sessionEmployeeId && _hubUri == HubUri()) return;

            await StopCoreAsync();
            if (employeeId is null) return;

            _sessionEmployeeId = employeeId;
            _hubUri = HubUri();
            _cts = new CancellationTokenSource();
            _hub = BuildHub();
            await TryStartHubAsync(_cts.Token);
            _pollLoop = PollLoopAsync(_cts.Token);
        }
        finally
        {
            _lifecycle.Release();
        }
    }

    /// <summary>Vuelve a consultar el contador (p. ej. después de marcar como leída).</summary>
    public async Task RefreshAsync(CancellationToken ct = default)
    {
        if (!_auth.IsAuthenticated) return;
        try
        {
            SetUnread(await _api.Client.UnreadCountAsync(ct));
        }
        catch (ApiException ex) when (ex.Status == HttpStatusCode.Unauthorized)
        {
            await _auth.HandleUnauthorizedAsync();
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or ApiException)
        {
            _logger.LogDebug(ex, "No se pudo actualizar el contador de notificaciones.");
        }
    }

    public void SetUnread(int count)
    {
        if (count < 0) count = 0;
        if (count == UnreadCount) return;
        UnreadCount = count;
        Changed?.Invoke();
    }

    private Uri HubUri() => new(_settings.BaseUri, "hubs/notifications");

    private HubConnection BuildHub()
    {
        var hub = new HubConnectionBuilder()
            .WithUrl(_hubUri ?? HubUri(), options => options.AccessTokenProvider = () => Task.FromResult(_api.AccessToken))
            .WithAutomaticReconnect()
            .AddJsonProtocol(o => o.PayloadSerializerOptions.Converters.Add(new JsonStringEnumConverter()))
            .Build();

        hub.On<NotificationDto>("notification", notification =>
        {
            SetUnread(UnreadCount + (notification.IsRead ? 0 : 1));
            Received?.Invoke(notification);
        });
        hub.Reconnected += async _ =>
        {
            Changed?.Invoke();
            await RefreshAsync();
        };
        hub.Reconnecting += _ => { Changed?.Invoke(); return Task.CompletedTask; };
        hub.Closed += _ => { Changed?.Invoke(); return Task.CompletedTask; };
        return hub;
    }

    private async Task TryStartHubAsync(CancellationToken ct)
    {
        if (_hub is null || _hub.State != HubConnectionState.Disconnected) return;
        try
        {
            await _hub.StartAsync(ct);
            Changed?.Invoke();
        }
        catch (Exception ex) when (ex is not OperationCanceledException || !ct.IsCancellationRequested)
        {
            // Sin tiempo real (servidor inaccesible, proxy sin WebSockets…): el sondeo de 60 s mantiene el contador.
            _logger.LogInformation(ex, "No se pudo conectar al hub de notificaciones; se usará sondeo.");
        }
    }

    private async Task PollLoopAsync(CancellationToken ct)
    {
        await RefreshAsync(ct);
        using var timer = new PeriodicTimer(PollInterval);
        try
        {
            while (await timer.WaitForNextTickAsync(ct))
            {
                await RefreshAsync(ct);
                await TryStartHubAsync(ct);
            }
        }
        catch (OperationCanceledException)
        {
            // Sesión cerrada.
        }
    }

    private async Task StopCoreAsync()
    {
        _sessionEmployeeId = null;
        _hubUri = null;
        if (_cts is not null)
        {
            await _cts.CancelAsync();
            if (_pollLoop is not null)
            {
                try { await _pollLoop; } catch (OperationCanceledException) { }
            }
            _cts.Dispose();
            _cts = null;
            _pollLoop = null;
        }
        if (_hub is not null)
        {
            try { await _hub.DisposeAsync(); }
            catch (Exception ex) { _logger.LogDebug(ex, "Error al cerrar el hub de notificaciones."); }
            _hub = null;
        }
        if (UnreadCount != 0)
        {
            UnreadCount = 0;
            Changed?.Invoke();
        }
    }

    public async ValueTask DisposeAsync()
    {
        _auth.Changed -= OnAuthChanged;
        _settings.Changed -= OnAuthChanged;
        await _lifecycle.WaitAsync();
        try { await StopCoreAsync(); }
        finally { _lifecycle.Release(); }
    }
}
