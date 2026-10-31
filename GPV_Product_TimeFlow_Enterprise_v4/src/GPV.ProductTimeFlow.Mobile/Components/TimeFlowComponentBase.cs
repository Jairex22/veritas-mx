using System.Net;
using GPV.ProductTimeFlow.Mobile.Services;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.Logging;

namespace GPV.ProductTimeFlow.Mobile.Components;

/// <summary>
/// Base de las páginas: acceso a la API, estado de carga y manejo uniforme de errores
/// (ApiException.Errors, 401 → cierre de sesión, servidor inaccesible, tiempo de espera).
/// </summary>
public abstract class TimeFlowComponentBase : ComponentBase, IDisposable
{
    private readonly CancellationTokenSource _disposeCts = new();
    private bool _disposed;

    [Inject] protected TimeFlowApi Api { get; set; } = default!;
    [Inject] protected AuthState Auth { get; set; } = default!;
    [Inject] protected NavigationManager Nav { get; set; } = default!;
    [Inject] protected ToastService Toasts { get; set; } = default!;
    [Inject] protected ILoggerFactory LoggerFactory { get; set; } = default!;

    /// <summary>Cliente vigente (se vuelve a leer en cada llamada porque cambia si el usuario cambia de servidor).</summary>
    protected TimeFlowApiClient Client => Api.Client;

    protected UserProfileDto? Profile => Auth.Profile;

    protected bool Busy { get; private set; }

    protected string? ErrorMessage { get; private set; }

    protected IReadOnlyList<string> ErrorDetails { get; private set; } = [];

    /// <summary>Se cancela al salir de la página.</summary>
    protected CancellationToken PageToken => _disposeCts.Token;

    protected void ClearError()
    {
        ErrorMessage = null;
        ErrorDetails = [];
    }

    protected void SetError(string message, IReadOnlyList<string>? details = null)
    {
        ErrorMessage = message;
        ErrorDetails = details?.Where(d => !string.IsNullOrWhiteSpace(d) && d != message).Distinct().ToList() ?? [];
    }

    /// <summary>
    /// Ejecuta una operación contra la API con indicador de ocupado y manejo de errores. Devuelve true si terminó bien.
    /// Mientras <see cref="Busy"/> es true no se aceptan nuevas operaciones (evita dobles envíos).
    /// </summary>
    protected async Task<bool> RunAsync(Func<CancellationToken, Task> action, bool trackBusy = true)
    {
        if (trackBusy)
        {
            if (Busy) return false;
            Busy = true;
        }
        ClearError();
        try
        {
            await action(PageToken);
            return true;
        }
        catch (Exception ex)
        {
            await HandleErrorAsync(ex);
            return false;
        }
        finally
        {
            if (trackBusy) Busy = false;
            if (!_disposed) StateHasChanged();
        }
    }

    /// <summary>Traduce cualquier excepción a un mensaje en español. Devuelve false si se ignoró (cancelación por salir).</summary>
    protected async Task<bool> HandleErrorAsync(Exception ex)
    {
        switch (ex)
        {
            case OperationCanceledException when PageToken.IsCancellationRequested:
                return false;
            case ApiException { Status: HttpStatusCode.Unauthorized }:
                await Auth.HandleUnauthorizedAsync();
                return true;
            case ApiException { Status: HttpStatusCode.Forbidden } api:
                SetError(api.Message is { Length: > 0 } m && !m.StartsWith("Error ", StringComparison.Ordinal) ? m : "No tienes permiso para realizar esta acción.", api.Errors);
                return true;
            case ApiException { Status: HttpStatusCode.TooManyRequests }:
                SetError("Demasiadas solicitudes en poco tiempo. Espera un minuto e inténtalo de nuevo.");
                return true;
            case ApiException api:
                SetError(api.Message, api.Errors);
                return true;
            case HttpRequestException:
                SetError($"No se pudo conectar con el servidor ({Api.BaseAddress.Authority}). Revisa tu conexión o la dirección del servidor en Ajustes.");
                return true;
            case TaskCanceledException or TimeoutException:
                SetError("El servidor tardó demasiado en responder. Inténtalo de nuevo.");
                return true;
            case UserFacingException user:
                SetError(user.Message);
                return true;
            default:
                LoggerFactory.CreateLogger(GetType()).LogError(ex, "Error no controlado en {Page}", GetType().Name);
                SetError("Ocurrió un error inesperado. Inténtalo de nuevo.");
                return true;
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        // Solo se cancela (no se libera): continuaciones pendientes aún pueden consultar el token sin ObjectDisposedException.
        _disposeCts.Cancel();
        OnDispose();
        GC.SuppressFinalize(this);
    }

    /// <summary>Liberar suscripciones a eventos en las páginas derivadas.</summary>
    protected virtual void OnDispose() { }
}
