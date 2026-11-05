using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;

namespace Gpv.Sqi.Config;

public sealed record Credential(string Username, string Password)
{
    // Nunca exponer la contraseña en logs o trazas.
    public override string ToString() => $"Credential {{ Username = {Username}, Password = *** }}";
}

public sealed class CredentialException(string message) : Exception(message);

/// <summary>
/// Credenciales sin código, config ni SQLite:
/// - env: GPV_ODATA_USER / GPV_ODATA_PASSWORD
/// - windows_credential_manager: credencial genérica del usuario (sin permisos de administrador).
/// </summary>
public static class Credentials
{
    public const string EnvUser = "GPV_ODATA_USER";
    public const string EnvPassword = "GPV_ODATA_PASSWORD";

    public static Credential? FromEnv()
    {
        var u = Environment.GetEnvironmentVariable(EnvUser)?.Trim();
        var p = Environment.GetEnvironmentVariable(EnvPassword);
        return !string.IsNullOrEmpty(u) && !string.IsNullOrEmpty(p) ? new Credential(u, p) : null;
    }

    public static Credential? Get(AppConfig cfg) => cfg.Str("odata.credential_source") switch
    {
        "env" => FromEnv(),
        "windows_credential_manager" => OperatingSystem.IsWindows()
            ? WinCred.Read(cfg.Str("odata.credential_target"))
            : throw new CredentialException("El Administrador de credenciales solo está disponible en Windows"),
        var s => throw new CredentialException($"Fuente de credenciales no soportada: {s}"),
    };

    public static bool IsConfigured(AppConfig cfg)
    {
        try { return Get(cfg) is not null; }
        catch (CredentialException) { return false; }
    }

    public static void Save(string target, string user, string password)
    {
        if (!OperatingSystem.IsWindows()) throw new CredentialException("El Administrador de credenciales solo está disponible en Windows");
        WinCred.Write(target, user, password);
    }

    [SupportedOSPlatform("windows")]
    private static class WinCred
    {
        private const int CredTypeGeneric = 1;
        private const int CredPersistLocalMachine = 2;

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct CREDENTIAL
        {
            public int Flags;
            public int Type;
            public string TargetName;
            public string? Comment;
            public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
            public int CredentialBlobSize;
            public IntPtr CredentialBlob;
            public int Persist;
            public int AttributeCount;
            public IntPtr Attributes;
            public string? TargetAlias;
            public string UserName;
        }

        [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CredRead(string target, int type, int flags, out IntPtr credential);

        [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CredWrite(ref CREDENTIAL credential, int flags);

        [DllImport("advapi32.dll")]
        private static extern void CredFree(IntPtr buffer);

        public static Credential? Read(string target)
        {
            if (!CredRead(target, CredTypeGeneric, 0, out var ptr)) return null;
            try
            {
                var c = Marshal.PtrToStructure<CREDENTIAL>(ptr);
                var pwd = c.CredentialBlobSize > 0 ? Marshal.PtrToStringUni(c.CredentialBlob, c.CredentialBlobSize / 2) : "";
                return new Credential(c.UserName ?? "", pwd);
            }
            finally { CredFree(ptr); }
        }

        public static void Write(string target, string user, string password)
        {
            var blob = Encoding.Unicode.GetBytes(password);
            var buf = Marshal.AllocHGlobal(blob.Length);
            try
            {
                Marshal.Copy(blob, 0, buf, blob.Length);
                var cred = new CREDENTIAL
                {
                    Type = CredTypeGeneric, TargetName = target, CredentialBlobSize = blob.Length,
                    CredentialBlob = buf, Persist = CredPersistLocalMachine, UserName = user,
                };
                if (!CredWrite(ref cred, 0)) throw new CredentialException($"CredWriteW falló (código {Marshal.GetLastWin32Error()})");
            }
            finally
            {
                Array.Clear(blob);
                Marshal.FreeHGlobal(buf);
            }
        }
    }
}
