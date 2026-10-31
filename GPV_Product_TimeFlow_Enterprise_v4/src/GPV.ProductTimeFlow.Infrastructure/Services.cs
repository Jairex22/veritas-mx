using System.Collections.Concurrent;
using System.Security.Cryptography;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Options;
using QRCoder;

namespace GPV.ProductTimeFlow.Infrastructure;

/// <summary>PBKDF2 (ASP.NET Core Identity v3, 100 000 iteraciones, HMAC-SHA512).</summary>
public sealed class PasswordService : IPasswordService
{
    private readonly PasswordHasher<UserAccount> _hasher = new(Options.Create(new PasswordHasherOptions { IterationCount = 100_000 }));
    public string Hash(string password) => _hasher.HashPassword(null!, password);
    public bool Verify(string hash, string password)
    {
        try { return _hasher.VerifyHashedPassword(null!, hash, password) != PasswordVerificationResult.Failed; }
        catch (FormatException) { return false; }
    }
}

/// <summary>
/// Almacenamiento local de adjuntos con nombres aleatorios (nunca se usa el nombre original en disco).
/// En producción puede sustituirse por un recurso compartido corporativo o Azure Blob con la misma interfaz.
/// </summary>
public sealed class LocalFileStorage(IOptions<StorageOptions> options) : IFileStorage
{
    private string Root => Path.GetFullPath(options.Value.AttachmentsRoot);

    public async Task<StoredFile> SaveAsync(Stream content, string extension, CancellationToken ct)
    {
        Directory.CreateDirectory(Root);
        var key = $"{DateTime.UtcNow:yyyyMM}/{Guid.NewGuid():N}{extension}";
        var path = Resolve(key);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        using var sha = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        long size = 0;
        await using (var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 81920, useAsync: true))
        {
            var buffer = new byte[81920];
            int read;
            while ((read = await content.ReadAsync(buffer, ct)) > 0)
            {
                sha.AppendData(buffer, 0, read);
                await file.WriteAsync(buffer.AsMemory(0, read), ct);
                size += read;
            }
        }
        return new StoredFile(key, size, Convert.ToHexStringLower(sha.GetHashAndReset()));
    }

    public Task<Stream?> OpenReadAsync(string storageKey, CancellationToken ct)
    {
        var path = Resolve(storageKey);
        return Task.FromResult<Stream?>(File.Exists(path) ? new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, useAsync: true) : null);
    }

    private string Resolve(string key)
    {
        var full = Path.GetFullPath(Path.Combine(Root, key));
        if (!full.StartsWith(Root, StringComparison.Ordinal)) throw new UnauthorizedAccessException("Ruta de almacenamiento inválida.");
        return full;
    }
}

public sealed class StorageOptions
{
    public string AttachmentsRoot { get; set; } = "App_Data/attachments";
}

public sealed class QrCodeGeneratorService : IQrCodeGenerator
{
    public byte[] Png(string content)
    {
        using var generator = new QRCodeGenerator();
        using var data = generator.CreateQrCode(content, QRCodeGenerator.ECCLevel.M);
        return new PngByteQRCode(data).GetGraphic(6, [17, 24, 39], [255, 255, 255], drawQuietZones: true);
    }
}

// ── Tiempo real (SignalR + bus interno para Blazor Server) ─────────────────────

/// <summary>Hub de notificaciones. Cada usuario se une a su grupo "employee:{id}" al conectarse.</summary>
[Authorize]
public sealed class NotificationHub : Hub
{
    public const string Path = "/hubs/notifications";
    public override async Task OnConnectedAsync()
    {
        var id = Context.User?.FindFirst(TimeFlowClaims.EmployeeId)?.Value;
        if (id is not null) await Groups.AddToGroupAsync(Context.ConnectionId, Group(int.Parse(id)));
        await base.OnConnectedAsync();
    }
    public static string Group(int employeeId) => $"employee:{employeeId}";
}

public static class TimeFlowClaims
{
    public const string EmployeeId = "tf:eid";
    public const string Roles = "tf:roles";
    public const string SecurityStamp = "tf:stamp";
}

/// <summary>Bus en memoria para que los circuitos de Blazor Server reciban avisos del mismo proceso.</summary>
public sealed class InProcessNotificationBus
{
    private readonly ConcurrentDictionary<Guid, (int EmployeeId, Func<NotificationDto, Task> Handler)> _subscribers = new();

    public IDisposable Subscribe(int employeeId, Func<NotificationDto, Task> handler)
    {
        var id = Guid.NewGuid();
        _subscribers[id] = (employeeId, handler);
        return new Subscription(() => _subscribers.TryRemove(id, out _));
    }

    public async Task PublishAsync(int employeeId, NotificationDto notification)
    {
        foreach (var (_, sub) in _subscribers)
        {
            if (sub.EmployeeId != employeeId) continue;
            try { await sub.Handler(notification); } catch { /* el circuito pudo cerrarse */ }
        }
    }

    private sealed class Subscription(Action dispose) : IDisposable { public void Dispose() => dispose(); }
}

public sealed class RealtimeNotifier(IHubContext<NotificationHub> hub, InProcessNotificationBus bus) : IRealtimeNotifier
{
    public async Task PushAsync(IReadOnlyCollection<(int EmployeeId, NotificationDto Notification)> items, CancellationToken ct)
    {
        foreach (var (employeeId, n) in items)
        {
            await bus.PublishAsync(employeeId, n);
            await hub.Clients.Group(NotificationHub.Group(employeeId)).SendAsync("notification", n, ct);
        }
    }
}
