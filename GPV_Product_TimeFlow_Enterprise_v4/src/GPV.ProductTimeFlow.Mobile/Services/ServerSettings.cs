using Microsoft.Maui.Devices;
using Microsoft.Maui.Storage;

namespace GPV.ProductTimeFlow.Mobile.Services;

/// <summary>
/// Dirección del servidor de la API, persistida con <see cref="Preferences"/>.
/// Valores por defecto (DEMO): el emulador de Android ve el equipo anfitrión como 10.0.2.2; iOS (simulador) usa localhost.
/// </summary>
public sealed class ServerSettings
{
    private const string ServerUrlKey = "timeflow.server_url";
    private const string EnvironmentModeKey = "timeflow.last_environment_mode";

    /// <summary>Hosts a los que la plataforma permite HTTP sin cifrar (ver network_security_config.xml e Info.plist).</summary>
    private static readonly string[] CleartextHosts = ["10.0.2.2", "localhost"];

    private Uri _baseUri;

    public ServerSettings()
    {
        var stored = Preferences.Default.Get<string?>(ServerUrlKey, null);
        _baseUri = stored is not null && TryNormalize(stored, out var uri, out _) ? uri! : new Uri(DefaultUrl);
    }

    /// <summary>Se dispara cuando cambia la URL del servidor.</summary>
    public event Action? Changed;

    public static string DefaultUrl =>
        DeviceInfo.Current.Platform == DevicePlatform.Android ? "http://10.0.2.2:5201/" : "http://localhost:5201/";

    public Uri BaseUri => _baseUri;

    public bool IsDefault => _baseUri.AbsoluteUri == new Uri(DefaultUrl).AbsoluteUri;

    /// <summary>
    /// Último modo de ambiente informado por el servidor ("Demo", "Production", …). Se usa en la pantalla de inicio
    /// de sesión, antes de autenticarse, para decidir si se muestran las cuentas sintéticas de DEMO.
    /// </summary>
    public string? LastEnvironmentMode
    {
        get => Preferences.Default.Get<string?>(EnvironmentModeKey, null);
        set
        {
            if (string.IsNullOrWhiteSpace(value)) Preferences.Default.Remove(EnvironmentModeKey);
            else Preferences.Default.Set(EnvironmentModeKey, value);
        }
    }

    /// <summary>Valida y guarda una nueva URL. Devuelve el mensaje de error (en español) si no es válida.</summary>
    public bool TryUpdate(string input, out string? error)
    {
        if (!TryNormalize(input, out var uri, out error)) return false;
        if (uri!.AbsoluteUri == _baseUri.AbsoluteUri) return true;

        _baseUri = uri;
        Preferences.Default.Set(ServerUrlKey, uri.AbsoluteUri);
        // Otro servidor puede ser otro ambiente: se vuelve a mostrar el aviso DEMO hasta conocer el modo real.
        LastEnvironmentMode = null;
        Changed?.Invoke();
        return true;
    }

    public void ResetToDefault()
    {
        Preferences.Default.Remove(ServerUrlKey);
        var uri = new Uri(DefaultUrl);
        if (uri.AbsoluteUri == _baseUri.AbsoluteUri) return;
        _baseUri = uri;
        LastEnvironmentMode = null;
        Changed?.Invoke();
    }

    public static bool TryNormalize(string? input, out Uri? uri, out string? error)
    {
        uri = null;
        error = null;
        var text = input?.Trim() ?? "";
        if (text.Length == 0)
        {
            error = "Escribe la dirección del servidor.";
            return false;
        }
        if (!text.Contains("://", StringComparison.Ordinal)) text = "http://" + text;
        if (!text.EndsWith('/')) text += "/";

        if (!Uri.TryCreate(text, UriKind.Absolute, out var parsed) || (parsed.Scheme != Uri.UriSchemeHttp && parsed.Scheme != Uri.UriSchemeHttps))
        {
            error = "La dirección no es válida. Ejemplo: https://timeflow.miempresa.com/";
            return false;
        }
        if (!string.IsNullOrEmpty(parsed.Query) || !string.IsNullOrEmpty(parsed.Fragment))
        {
            error = "La dirección no debe incluir parámetros (?…) ni fragmentos (#…).";
            return false;
        }
        if (parsed.Scheme == Uri.UriSchemeHttp && !CleartextHosts.Contains(parsed.Host, StringComparer.OrdinalIgnoreCase))
        {
            error = "Solo se permite HTTP sin cifrar hacia 10.0.2.2 o localhost (DEMO). Para cualquier otro servidor usa HTTPS.";
            return false;
        }
        uri = parsed;
        return true;
    }
}
