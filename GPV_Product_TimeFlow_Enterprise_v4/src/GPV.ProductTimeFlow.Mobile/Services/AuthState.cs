using System.Globalization;
using System.Net;
using System.Text.Json;
using GPV.ProductTimeFlow.Shared;
using Microsoft.Extensions.Logging;
using Microsoft.Maui.Storage;

namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>
/// Estado de la sesión: token JWT (en <see cref="SecureStorage"/>) y perfil del usuario.
/// Cierra la sesión automáticamente ante un 401 (<see cref="HandleUnauthorizedAsync"/>).
/// </summary>
public sealed class AuthState(TimeFlowApi api, ServerSettings settings, ILogger<AuthState> logger)
{
    private const string TokenKey = "timeflow.access_token";
    private const string ExpiresKey = "timeflow.access_token_expires";
    private const string ProfileKey = "timeflow.profile";

    private readonly SemaphoreSlim _initGate = new(1, 1);
    private string? _token;
    private DateTime _expiresAtUtc;

    /// <summary>Se dispara al iniciar o cerrar sesión.</summary>
    public event Action? Changed;

    public UserProfileDto? Profile { get; private set; }

    public bool IsInitialized { get; private set; }

    public bool IsAuthenticated => Profile is not null && _token is not null && _expiresAtUtc > DateTime.UtcNow;

    /// <summary>Mensaje para la pantalla de inicio de sesión cuando la sesión terminó sin que el usuario la cerrara.</summary>
    public string? SignOutReason { get; private set; }

    /// <summary>True si el almacenamiento seguro no estuvo disponible: la sesión vive solo en memoria.</summary>
    public bool SecureStorageUnavailable { get; private set; }

    public bool HasRole(UserRole role) => Profile is not null && (Profile.Roles & role) == role;

    public bool IsApprover => HasRole(UserRole.DirectSupervisor) || HasRole(UserRole.SeniorManager);

    /// <summary>La API permite la bandeja administrativa a Registro administrativo y a Administración de Producto.</summary>
    public bool CanUseAdministrativeInbox => HasRole(UserRole.AdministrativeRegistrar) || HasRole(UserRole.ProductAdmin);

    /// <summary>Restaura la sesión guardada (una sola vez por ejecución).</summary>
    public async Task InitializeAsync(CancellationToken ct = default)
    {
        if (IsInitialized) return;
        await _initGate.WaitAsync(ct);
        try
        {
            if (IsInitialized) return;
            await RestoreAsync(ct);
            IsInitialized = true;
        }
        finally
        {
            _initGate.Release();
        }
        Changed?.Invoke();
    }

    private async Task RestoreAsync(CancellationToken ct)
    {
        string? token, expires, profileJson;
        try
        {
            token = await SecureStorage.Default.GetAsync(TokenKey);
            expires = await SecureStorage.Default.GetAsync(ExpiresKey);
            profileJson = await SecureStorage.Default.GetAsync(ProfileKey);
        }
        catch (Exception ex)
        {
            // Puede ocurrir si el Keystore/Keychain se invalidó (p. ej. restauración del dispositivo).
            logger.LogWarning(ex, "No se pudo leer la sesión guardada; se descarta.");
            SecureStorage.Default.RemoveAll();
            return;
        }

        if (token is null
            || !DateTime.TryParse(expires, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out var expiresAtUtc)
            || expiresAtUtc <= DateTime.UtcNow.AddMinutes(1))
        {
            ClearStorage();
            return;
        }

        UserProfileDto? cached = null;
        if (profileJson is not null)
        {
            try { cached = JsonSerializer.Deserialize<UserProfileDto>(profileJson, TimeFlowJson.Options); }
            catch (JsonException) { cached = null; }
        }

        api.SetToken(token);
        try
        {
            // Revalida contra el servidor: si la cuenta se desactivó o cambiaron sus roles, la API responde 401.
            var profile = await api.Client.MeAsync(ct);
            Apply(token, expiresAtUtc, profile);
            await PersistAsync();
        }
        catch (ApiException ex) when (ex.Status == HttpStatusCode.Unauthorized)
        {
            api.SetToken(null);
            ClearStorage();
            SignOutReason = "Tu sesión expiró. Inicia sesión de nuevo.";
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException && cached is not null)
        {
            // Sin conexión: se usa el perfil guardado; la siguiente llamada a la API volverá a validar el token.
            logger.LogInformation(ex, "Servidor no disponible al restaurar la sesión; se usa el perfil guardado.");
            Apply(token, expiresAtUtc, cached!);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "No se pudo restaurar la sesión.");
            api.SetToken(null);
        }
    }

    public async Task LoginAsync(string email, string password, CancellationToken ct = default)
    {
        var response = await api.Client.LoginAsync(new LoginRequest { Email = email.Trim(), Password = password }, ct);
        Apply(response.AccessToken, response.ExpiresAtUtc, response.Profile);
        SignOutReason = null;
        settings.LastEnvironmentMode = response.Profile.EnvironmentMode;
        await PersistAsync();
        Changed?.Invoke();
    }

    public Task LogoutAsync() => SignOutAsync(reason: null);

    /// <summary>Llamar cuando la API responde 401: la sesión ya no es válida.</summary>
    public Task HandleUnauthorizedAsync() =>
        IsAuthenticated || _token is not null ? SignOutAsync("Tu sesión expiró o fue revocada. Inicia sesión de nuevo.") : Task.CompletedTask;

    private Task SignOutAsync(string? reason)
    {
        Profile = null;
        _token = null;
        _expiresAtUtc = default;
        SignOutReason = reason;
        api.SetToken(null);
        ClearStorage();
        Changed?.Invoke();
        return Task.CompletedTask;
    }

    private void Apply(string token, DateTime expiresAtUtc, UserProfileDto profile)
    {
        _token = token;
        _expiresAtUtc = expiresAtUtc.Kind == DateTimeKind.Utc ? expiresAtUtc : DateTime.SpecifyKind(expiresAtUtc, DateTimeKind.Utc);
        Profile = profile;
        api.SetToken(token);
    }

    private async Task PersistAsync()
    {
        if (_token is null || Profile is null) return;
        try
        {
            await SecureStorage.Default.SetAsync(TokenKey, _token);
            await SecureStorage.Default.SetAsync(ExpiresKey, _expiresAtUtc.ToString("O", CultureInfo.InvariantCulture));
            await SecureStorage.Default.SetAsync(ProfileKey, JsonSerializer.Serialize(Profile, TimeFlowJson.Options));
            SecureStorageUnavailable = false;
        }
        catch (Exception ex)
        {
            // Sin almacenamiento seguro la sesión sigue en memoria y se pierde al cerrar la app (no se guarda en texto plano).
            logger.LogWarning(ex, "SecureStorage no disponible; la sesión no se conservará al cerrar la app.");
            SecureStorageUnavailable = true;
        }
    }

    private void ClearStorage()
    {
        try
        {
            SecureStorage.Default.Remove(TokenKey);
            SecureStorage.Default.Remove(ExpiresKey);
            SecureStorage.Default.Remove(ProfileKey);
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "No se pudo limpiar el almacenamiento seguro.");
        }
    }
}
