using System.Globalization;
using GPV.ProductTimeFlow.Mobile.Services;
using Microsoft.Extensions.Logging;

namespace GPV.ProductTimeFlow.Mobile;

public static class MauiProgram
{
    public static MauiApp CreateMauiApp()
    {
        // Toda la interfaz se muestra en español de México (fechas, números y nombres de meses).
        var culture = CultureInfo.GetCultureInfo("es-MX");
        CultureInfo.DefaultThreadCurrentCulture = culture;
        CultureInfo.DefaultThreadCurrentUICulture = culture;

        var builder = MauiApp.CreateBuilder();
        builder.UseMauiApp<App>();

        builder.Services.AddMauiBlazorWebView();
#if DEBUG
        builder.Services.AddBlazorWebViewDeveloperTools();
        builder.Logging.AddDebug();
        builder.Logging.SetMinimumLevel(LogLevel.Debug);
#endif

        // Configuración (URL del servidor persistida con Preferences).
        builder.Services.AddSingleton<ServerSettings>();

        // Cliente HTTP tipado de la API. TimeFlowApi crea el HttpClient (BaseAddress = ServerSettings.BaseUri)
        // y lo reconstruye cuando el usuario cambia la URL del servidor: HttpClient no admite cambiar BaseAddress
        // después de la primera petición.
        builder.Services.AddSingleton<TimeFlowApi>();

        // Sesión (JWT en SecureStorage + perfil), notificaciones en tiempo real, avisos y archivos del dispositivo.
        builder.Services.AddSingleton<AuthState>();
        builder.Services.AddSingleton<NotificationCenter>();
        builder.Services.AddSingleton<ToastService>();
        builder.Services.AddSingleton<DeviceFiles>();

        return builder.Build();
    }
}
