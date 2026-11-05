using System.Diagnostics;
using System.Net;
using Gpv.Sqi.Api;
using Gpv.Sqi.Config;
using Gpv.Sqi.Infrastructure;
using Gpv.Sqi.Services;

namespace Gpv.Sqi;

/// <summary>
/// GPV SMT Quality Intelligence — punto de entrada.
///   GPV.SMT.QualityIntelligence.exe                     inicia el servidor local y abre el navegador
///   GPV.SMT.QualityIntelligence.exe --no-browser
///   GPV.SMT.QualityIntelligence.exe --port 8800
///   GPV.SMT.QualityIntelligence.exe --set-credential    guarda usuario/contraseña en el Administrador de credenciales de Windows
///   GPV.SMT.QualityIntelligence.exe --check             verifica la configuración y sale
/// </summary>
public static class Program
{
    /// <summary>
    /// Carpeta de trabajo: la que contiene config.json (directorio actual o carpeta del ejecutable).
    /// Base de datos y logs se crean ahí.
    /// </summary>
    public static string ResolveRoot()
    {
        var cwd = Directory.GetCurrentDirectory();
        if (File.Exists(Path.Combine(cwd, "config.json"))) return cwd;
        return AppContext.BaseDirectory;
    }

    public static async Task<int> Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        int? port = null; var noBrowser = false; var setCredential = false; var check = false;
        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--port" when i + 1 < args.Length && int.TryParse(args[i + 1], out var p): port = p; i++; break;
                case "--no-browser": noBrowser = true; break;
                case "--set-credential": setCredential = true; break;
                case "--check": check = true; break;
                case "--help" or "-h" or "/?":
                    Console.WriteLine("Uso: GPV.SMT.QualityIntelligence [--port N] [--no-browser] [--set-credential] [--check]");
                    return 0;
                default:
                    Console.Error.WriteLine($"Argumento no reconocido: {args[i]}");
                    return 2;
            }
        }

        var root = ResolveRoot();
        AppConfig cfg;
        try { cfg = AppConfig.Load(Path.Combine(root, "config.json"), root); }
        catch (ConfigException ex)
        {
            Console.Error.WriteLine($"ERROR de configuración: {ex.Message}");
            return 2;
        }

        if (setCredential) return SetCredential(cfg);

        AppLog.Init(cfg.ResolvePath("logs"));
        var host = cfg.Str("server.host");
        var listenPort = port ?? cfg.Int("server.port");
        if (!IPAddress.TryParse(host, out var ip))
        {
            Console.Error.WriteLine("server.host debe ser una dirección IP (recomendado 127.0.0.1)");
            return 2;
        }
        if (!IPAddress.IsLoopback(ip)) AppLog.Warn("main", $"ATENCIÓN: el servidor escuchará en {host} (no loopback). Requiere aprobación de TI.");

        var ctx = new AppServices(cfg);
        if (check)
        {
            Console.WriteLine($"GPV SMT Quality Intelligence v{AppConfig.AppVersion} | modo={ctx.Config.Mode} | base={ctx.Config.Str("odata.base_url")} | " +
                              $"auth={ctx.Config.Str("odata.auth_method")} | live_mode_approved={ctx.Config.Bool("security.live_mode_approved")} | " +
                              $"allow_basic_auth_over_http={ctx.Config.Bool("security.allow_basic_auth_over_http")} | " +
                              $"config={(File.Exists(Path.Combine(root, "config.json")) ? Path.Combine(root, "config.json") : "(no existe config.json: valores por defecto)")} | " +
                              $"db={cfg.ResolvePath("database")}");
            return 0;
        }

        var app = WebServer.Build(ctx, host, listenPort);
        var url = $"http://{(ip.Equals(IPAddress.Any) ? "127.0.0.1" : host)}:{listenPort}/";
        try { await app.StartAsync(); }
        catch (IOException ex)
        {
            Console.Error.WriteLine($"No se pudo iniciar en el puerto {listenPort}: {ex.Message}. Pruebe con --port 8800");
            return 3;
        }
        AppLog.Info("main", $"GPV SMT Quality Intelligence v{AppConfig.AppVersion} escuchando en {url} (modo {ctx.Config.Mode})");
        if (ctx.Config.Mode == "demo") AppLog.Info("main", "MODO DEMOSTRACIÓN: no se consulta FactoryLogix; los datos son de ejemplo.");
        Console.WriteLine($"\n  Abra {url} en el navegador.  Ctrl+C para detener.\n");
        if (cfg.Bool("server.open_browser") && !noBrowser)
        {
            try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); }
            catch (Exception) { /* abrir el navegador es opcional */ }
        }
        await app.WaitForShutdownAsync();
        AppLog.Info("main", "Detenido por el usuario");
        return 0;
    }

    private static int SetCredential(AppConfig cfg)
    {
        var target = cfg.Str("odata.credential_target");
        Console.Write("Usuario FactoryLogix: ");
        var user = (Console.ReadLine() ?? "").Trim();
        Console.Write("Contraseña (no se mostrará): ");
        var pwd = ReadHidden();
        try { Credentials.Save(target, user, pwd); }
        catch (CredentialException ex)
        {
            Console.Error.WriteLine($"No se pudo guardar la credencial: {ex.Message}");
            return 3;
        }
        Console.WriteLine($"Credencial guardada en el Administrador de credenciales de Windows como '{target}'.");
        Console.WriteLine("Configure odata.credential_source = windows_credential_manager.");
        return 0;
    }

    private static string ReadHidden()
    {
        if (Console.IsInputRedirected) return Console.ReadLine() ?? "";
        var sb = new System.Text.StringBuilder();
        while (true)
        {
            var k = Console.ReadKey(intercept: true);
            if (k.Key == ConsoleKey.Enter) { Console.WriteLine(); return sb.ToString(); }
            if (k.Key == ConsoleKey.Backspace) { if (sb.Length > 0) sb.Length--; continue; }
            if (!char.IsControl(k.KeyChar)) sb.Append(k.KeyChar);
        }
    }
}
