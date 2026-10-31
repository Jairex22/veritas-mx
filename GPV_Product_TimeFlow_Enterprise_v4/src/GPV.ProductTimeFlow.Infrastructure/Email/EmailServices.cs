using System.Net;
using Azure.Identity;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.Graph;
using Microsoft.Graph.Models;
using Microsoft.Graph.Users.Item.SendMail;

namespace GPV.ProductTimeFlow.Infrastructure.Email;

public sealed class EmailOptions
{
    public const string Section = "Email";
    /// <summary>"Mock" (demo, no envía) o "Graph" (Microsoft Graph, envío real).</summary>
    public string Provider { get; set; } = "Mock";
    /// <summary>Solo un host debe procesar la cola (por defecto la aplicación Web).</summary>
    public bool ProcessorEnabled { get; set; } = true;
    public int PollSeconds { get; set; } = 10;
    public int MaxAttempts { get; set; } = 6;
    public int BatchSize { get; set; } = 20;
    public string MockDropFolder { get; set; } = "App_Data/mail-drop";
    public string BrandColor { get; set; } = "#1F4FD8";
    public GraphMailOptions Graph { get; set; } = new();
    public bool RemindersEnabled { get; set; } = true;
    public int ReminderIntervalMinutes { get; set; } = 60;
}

public sealed class GraphMailOptions
{
    public string? TenantId { get; set; }
    public string? ClientId { get; set; }
    /// <summary>Nunca en appsettings: usar variable de entorno Email__Graph__ClientSecret o Azure Key Vault.</summary>
    public string? ClientSecret { get; set; }
    /// <summary>Alternativa recomendada al secreto: certificado (.pfx) del registro de aplicación.</summary>
    public string? CertificatePath { get; set; }
    public string? CertificatePassword { get; set; }
    /// <summary>Buzón remitente (p. ej. buzón compartido timeflow@empresa). Requiere Mail.Send con Application Access Policy.</summary>
    public string? SenderMailbox { get; set; }
    public bool SaveToSentItems { get; set; } = true;
}

public sealed class EmailComposer(IOptions<EmailOptions> options) : IEmailComposer
{
    private static readonly Lazy<string> Template = new(() =>
    {
        using var stream = typeof(EmailComposer).Assembly.GetManifestResourceStream(
            typeof(EmailComposer).Assembly.GetManifestResourceNames().First(n => n.EndsWith("notification.html", StringComparison.Ordinal)))!;
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    });

    public (string Subject, string Html) Compose(EmailModel m)
    {
        static string E(string? v) => WebUtility.HtmlEncode(v ?? "");
        var prefix = m.EnvironmentLabel.StartsWith("PRODUCCIÓN", StringComparison.Ordinal) ? "" : "[DEMO] ";
        var subject = $"{prefix}{m.Folio} · {m.Title}";
        var approver = string.IsNullOrWhiteSpace(m.Approver) ? "" :
            $"<tr><td style=\"padding:10px 14px;color:#6b7280;\">Responsable</td><td style=\"padding:10px 14px;\">{E(m.Approver)}</td></tr>";
        var comment = string.IsNullOrWhiteSpace(m.Comment) ? "" :
            $"<tr><td style=\"padding:16px 28px 0 28px;\"><div style=\"background:#fff8eb;border:1px solid #fde3b0;border-radius:10px;padding:12px 14px;font-size:14px;color:#7c4a03;\"><strong>Comentarios:</strong> {E(m.Comment)}</div></td></tr>";
        var html = Template.Value
            .Replace("{{Subject}}", E(subject)).Replace("{{Preheader}}", E(m.Intro)).Replace("{{BrandColor}}", E(options.Value.BrandColor))
            .Replace("{{EnvironmentLabel}}", E(m.EnvironmentLabel)).Replace("{{Folio}}", E(m.Folio)).Replace("{{Title}}", E(m.Title))
            .Replace("{{Intro}}", E(m.Intro)).Replace("{{EmployeeName}}", E(m.EmployeeName)).Replace("{{RequestType}}", E(m.RequestType))
            .Replace("{{Dates}}", E(m.Dates)).Replace("{{Duration}}", E(m.Duration)).Replace("{{Reason}}", E(m.ReasonSummary))
            .Replace("{{Status}}", E(m.Status)).Replace("{{ApproverRow}}", approver).Replace("{{CommentBlock}}", comment)
            .Replace("{{Link}}", E(m.Link));
        return (subject, html);
    }
}

public sealed record SendResult(EmailStatus Status, string Provider, string? ProviderMessageId);

public interface IEmailSender
{
    string Name { get; }
    Task<SendResult> SendAsync(EmailOutboxMessage message, CancellationToken ct);
}

/// <summary>
/// Proveedor de DEMOSTRACIÓN. No envía correos: guarda el HTML en una carpeta local y marca el mensaje como
/// "MockDelivered" (Registrado en buzón DEMO), nunca como "Sent".
/// </summary>
public sealed class MockEmailSender(IOptions<EmailOptions> options, ILogger<MockEmailSender> logger) : IEmailSender
{
    public string Name => "Mock (demostración)";
    public async Task<SendResult> SendAsync(EmailOutboxMessage message, CancellationToken ct)
    {
        var folder = Path.GetFullPath(options.Value.MockDropFolder);
        Directory.CreateDirectory(folder);
        var file = Path.Combine(folder, $"{DateTime.UtcNow:yyyyMMdd_HHmmss}_{message.Folio}_{message.EventType}_{message.Id:N}.html");
        await File.WriteAllTextAsync(file, $"<!-- Para: {WebUtility.HtmlEncode(message.ToAddresses)} | CC: {WebUtility.HtmlEncode(message.CcAddresses)} | Asunto: {WebUtility.HtmlEncode(message.Subject)} -->\n{message.HtmlBody}", ct);
        logger.LogInformation("Correo DEMO registrado (no enviado) {EventType} {Folio} → {File}", message.EventType, message.Folio, Path.GetFileName(file));
        return new SendResult(EmailStatus.MockDelivered, Name, Path.GetFileName(file));
    }
}

/// <summary>
/// Envío real mediante Microsoft Graph (POST /users/{buzón}/sendMail) con flujo OAuth 2.0 client credentials.
/// Requiere registro de aplicación en Microsoft Entra ID con permiso de aplicación Mail.Send y consentimiento de TI.
/// </summary>
public sealed class GraphEmailSender : IEmailSender
{
    private readonly GraphServiceClient _client;
    private readonly GraphMailOptions _options;

    public GraphEmailSender(IOptions<EmailOptions> options)
    {
        _options = options.Value.Graph;
        if (string.IsNullOrWhiteSpace(_options.TenantId) || string.IsNullOrWhiteSpace(_options.ClientId) || string.IsNullOrWhiteSpace(_options.SenderMailbox))
            throw new InvalidOperationException("Configuración de Microsoft Graph incompleta (TenantId, ClientId, SenderMailbox).");
        Azure.Core.TokenCredential credential = !string.IsNullOrWhiteSpace(_options.CertificatePath)
            ? new ClientCertificateCredential(_options.TenantId, _options.ClientId, System.Security.Cryptography.X509Certificates.X509CertificateLoader.LoadPkcs12FromFile(_options.CertificatePath, _options.CertificatePassword))
            : new ClientSecretCredential(_options.TenantId, _options.ClientId, _options.ClientSecret
                ?? throw new InvalidOperationException("Falta Email__Graph__ClientSecret o Email__Graph__CertificatePath."));
        _client = new GraphServiceClient(credential, ["https://graph.microsoft.com/.default"]);
    }

    public string Name => "Microsoft Graph";

    public async Task<SendResult> SendAsync(EmailOutboxMessage message, CancellationToken ct)
    {
        static List<Recipient> Recipients(string? csv) => (csv ?? "").Split([',', ';'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(a => new Recipient { EmailAddress = new EmailAddress { Address = a } }).ToList();
        var body = new SendMailPostRequestBody
        {
            Message = new Message
            {
                Subject = message.Subject,
                Body = new ItemBody { ContentType = BodyType.Html, Content = message.HtmlBody },
                ToRecipients = Recipients(message.ToAddresses),
                CcRecipients = Recipients(message.CcAddresses),
                InternetMessageHeaders = [new InternetMessageHeader { Name = "X-TimeFlow-Message-Id", Value = message.Id.ToString("N") }]
            },
            SaveToSentItems = _options.SaveToSentItems
        };
        await _client.Users[_options.SenderMailbox].SendMail.PostAsync(body, cancellationToken: ct);
        return new SendResult(EmailStatus.Sent, Name, message.Id.ToString("N"));
    }
}

/// <summary>
/// Procesa la cola persistente de correo con reintentos exponenciales. Reclama cada mensaje con token de
/// concurrencia para que dos instancias nunca envíen el mismo correo.
/// </summary>
public sealed class EmailOutboxProcessor(IServiceScopeFactory scopes, IOptions<EmailOptions> options, ILogger<EmailOutboxProcessor> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!options.Value.ProcessorEnabled) { logger.LogInformation("Procesador de correo deshabilitado en este host."); return; }
        await Task.Delay(TimeSpan.FromSeconds(3), stoppingToken).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
        while (!stoppingToken.IsCancellationRequested)
        {
            try { await ProcessBatchAsync(stoppingToken); }
            catch (Exception ex) when (!stoppingToken.IsCancellationRequested) { logger.LogError(ex, "Error procesando la cola de correo"); }
            await Task.Delay(TimeSpan.FromSeconds(Math.Max(2, options.Value.PollSeconds)), stoppingToken).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
        }
    }

    public async Task<int> ProcessBatchAsync(CancellationToken ct)
    {
        using var scope = scopes.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<ITimeFlowDbContext>();
        var sender = scope.ServiceProvider.GetRequiredService<IEmailSender>();
        var now = DateTime.UtcNow;
        var batch = await db.EmailOutbox.Where(m => m.Status == EmailStatus.Pending && m.NextAttemptAtUtc <= now)
            .OrderBy(m => m.CreatedAtUtc).Take(options.Value.BatchSize).ToListAsync(ct);
        var processed = 0;
        foreach (var message in batch)
        {
            // Reclamar (Pending → Sending). Si otra instancia lo tomó, falla por concurrencia y se omite.
            message.Status = EmailStatus.Sending;
            message.Attempts++;
            message.ConcurrencyStamp = Guid.NewGuid();
            try { await db.SaveChangesAsync(ct); }
            catch (DbUpdateConcurrencyException) { continue; }

            try
            {
                var result = await sender.SendAsync(message, ct);
                message.Status = result.Status;
                message.Provider = result.Provider;
                message.ProviderMessageId = result.ProviderMessageId;
                message.SentAtUtc = DateTime.UtcNow;
                message.LastError = null;
            }
            catch (Exception ex) when (!ct.IsCancellationRequested)
            {
                var final = message.Attempts >= options.Value.MaxAttempts;
                message.Status = final ? EmailStatus.Failed : EmailStatus.Pending;
                message.Provider = sender.Name;
                message.LastError = Text.Summarize(ex.Message, 1900);
                message.NextAttemptAtUtc = DateTime.UtcNow.AddSeconds(Math.Min(3600, 15 * Math.Pow(2, message.Attempts)));
                logger.LogWarning(ex, "Fallo al enviar correo {Id} intento {Attempt}{Final}", message.Id, message.Attempts, final ? " (definitivo)" : "");
            }
            message.ConcurrencyStamp = Guid.NewGuid();
            await db.SaveChangesAsync(ct);
            processed++;
        }
        return processed;
    }
}

/// <summary>Recordatorios programados de solicitudes pendientes.</summary>
public sealed class ReminderBackgroundService(IServiceScopeFactory scopes, IOptions<EmailOptions> options, ILogger<ReminderBackgroundService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!options.Value.ProcessorEnabled || !options.Value.RemindersEnabled) return;
        await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = scopes.CreateScope();
                var count = await scope.ServiceProvider.GetRequiredService<ReminderService>().EnqueueRemindersAsync(stoppingToken);
                if (count > 0) logger.LogInformation("{Count} recordatorios generados", count);
            }
            catch (Exception ex) when (!stoppingToken.IsCancellationRequested) { logger.LogError(ex, "Error generando recordatorios"); }
            await Task.Delay(TimeSpan.FromMinutes(Math.Max(5, options.Value.ReminderIntervalMinutes)), stoppingToken).ConfigureAwait(ConfigureAwaitOptions.SuppressThrowing);
        }
    }
}
