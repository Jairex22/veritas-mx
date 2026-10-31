using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;

namespace GPV.ProductTimeFlow.Application;

/// <summary>
/// Crea notificaciones internas y mensajes de la cola de correo DENTRO de la misma unidad de trabajo que la
/// transición (patrón Outbox): si la transacción falla, no queda ningún aviso huérfano. El envío real lo hace
/// un proceso en segundo plano con reintentos. Tras confirmar la transacción se empujan los avisos en tiempo real.
/// </summary>
public sealed class NotificationDispatcher(
    ITimeFlowDbContext db,
    IEmailComposer composer,
    EnvironmentInfo env,
    LocalClock clock,
    SettingsService settings,
    IRealtimeNotifier realtime,
    ILogger<NotificationDispatcher> logger)
{
    private readonly List<(int EmployeeId, Notification Notification)> _pendingRealtime = [];

    /// <summary>Permite cargar datos de demostración sin generar avisos.</summary>
    public bool Suppressed { get; set; }

    public void Notify(int recipientId, NotificationType type, string title, string message, Request? request, string? dedupKey = null)
    {
        if (Suppressed || recipientId <= 0) return;
        var n = new Notification
        {
            Id = Guid.NewGuid(),
            RecipientEmployeeId = recipientId,
            Type = type,
            Title = title,
            Message = message,
            RequestId = request?.Id,
            Link = request is null ? null : $"/solicitudes/{request.Id}",
            CreatedAtUtc = clock.UtcNow,
            DeduplicationKey = dedupKey
        };
        db.Notifications.Add(n);
        _pendingRealtime.Add((recipientId, n));
    }

    public async Task EmailAsync(string eventType, string to, string? cc, Request request, string title, string intro, string? approver, string? comment, CancellationToken ct, string? dedupSuffix = null)
    {
        if (Suppressed || string.IsNullOrWhiteSpace(to)) return;
        var key = $"{request.Id:N}:{eventType}:v{request.Version}:{to.ToLowerInvariant()}{dedupSuffix}";
        if (db.EmailOutbox.Local.Any(m => m.DeduplicationKey == key) || await db.EmailOutbox.AnyAsync(m => m.DeduplicationKey == key, ct))
        {
            logger.LogInformation("Correo duplicado omitido {DedupKey}", key);
            return;
        }
        var p = request.PrimaryPeriod;
        var model = new EmailModel(
            title, intro, request.Folio, request.Employee?.FullName ?? "", Labels.Kind(request.Kind),
            p is null ? "" : Text.DateRange(p.StartDate, p.EndDate, request.IsFullDay ? null : p.StartTime, request.IsFullDay ? null : p.EndTime),
            Text.Duration(request.Kind, request.TotalHours, request.TotalDays, request.IsFullDay),
            Text.Summarize(request.Reason, 120), Labels.Status(request.Status), approver,
            $"{env.BaseUrl}/solicitudes/{request.Id}", Text.Summarize(comment, 300), env.Label);
        var (subject, html) = composer.Compose(model);
        db.EmailOutbox.Add(new EmailOutboxMessage
        {
            Id = Guid.NewGuid(),
            DeduplicationKey = key,
            ToAddresses = to,
            CcAddresses = cc,
            Subject = subject,
            HtmlBody = html,
            EventType = eventType,
            RequestId = request.Id,
            Folio = request.Folio,
            Status = EmailStatus.Pending,
            CreatedAtUtc = clock.UtcNow,
            NextAttemptAtUtc = clock.UtcNow
        });
    }

    /// <summary>Genera los avisos y correos obligatorios para cada evento del flujo.</summary>
    public async Task OnTransitionAsync(Request r, WorkflowAction action, Actor actor, string? comment, CancellationToken ct)
    {
        if (Suppressed) return;
        var employee = r.Employee!;
        var supervisor = r.AssignedSupervisor;
        var manager = r.AssignedManager;
        var kind = Labels.Kind(r.Kind).ToLowerInvariant();
        switch (action)
        {
            case WorkflowAction.Submit:
                Notify(employee.Id, NotificationType.RequestSubmitted, $"Solicitud {r.Folio} enviada", $"Tu solicitud de {kind} fue turnada a {supervisor?.FullName}.", r);
                if (supervisor is not null)
                {
                    Notify(supervisor.Id, NotificationType.RequestSubmitted, $"Nueva solicitud {r.Folio}", $"{employee.FullName} envió una solicitud de {kind} para tu revisión.", r);
                    await EmailAsync("submitted", supervisor.Email, null, r, "Nueva solicitud por autorizar",
                        $"{employee.FullName} envió una solicitud que requiere tu revisión como jefa directa (filtro 1).", supervisor.FullName, null, ct);
                }
                break;
            case WorkflowAction.SupervisorApprove:
                Notify(employee.Id, NotificationType.RequestApproved, $"{r.Folio} aprobada por jefa directa", $"{actor.Name} aprobó y firmó tu solicitud. Ahora la revisa {manager?.FullName}.", r);
                if (manager is not null)
                {
                    Notify(manager.Id, NotificationType.RequestSubmitted, $"Solicitud {r.Folio} por decidir", $"{actor.Name} aprobó la solicitud de {employee.FullName}. Requiere tu decisión final.", r);
                    await EmailAsync("supervisor-approved", manager.Email, null, r, "Solicitud pendiente de decisión final",
                        $"{actor.Name} (jefa directa) aprobó la solicitud de {employee.FullName}. Requiere tu autorización final (filtro 2).", actor.Name, comment, ct);
                }
                break;
            case WorkflowAction.SupervisorReject:
                Notify(employee.Id, NotificationType.RequestRejected, $"{r.Folio} rechazada", $"{actor.Name} rechazó tu solicitud.", r);
                await EmailAsync("supervisor-rejected", employee.Email, null, r, "Tu solicitud fue rechazada",
                    $"{actor.Name} (jefa directa) rechazó tu solicitud. Consulta la justificación en el expediente.", actor.Name, comment, ct);
                break;
            case WorkflowAction.SupervisorReturn:
            case WorkflowAction.ManagerReturn:
                Notify(employee.Id, NotificationType.RequestReturned, $"{r.Folio} devuelta para corrección", $"{actor.Name} devolvió tu solicitud con observaciones.", r);
                await EmailAsync(action == WorkflowAction.SupervisorReturn ? "supervisor-returned" : "manager-returned", employee.Email, null, r,
                    "Tu solicitud requiere corrección", $"{actor.Name} devolvió tu solicitud para que la corrijas y vuelvas a enviarla.", actor.Name, comment, ct);
                if (action == WorkflowAction.ManagerReturn && supervisor is not null)
                    Notify(supervisor.Id, NotificationType.RequestReturned, $"{r.Folio} devuelta por jefe superior", $"{actor.Name} devolvió la solicitud de {employee.FullName}.", r);
                break;
            case WorkflowAction.ManagerApprove:
            {
                var policy = await settings.GetPolicyAsync(ct);
                Notify(employee.Id, NotificationType.RequestApproved, $"{r.Folio} autorizada", $"{actor.Name} autorizó definitivamente tu solicitud. Se remitió a registro administrativo.", r);
                if (supervisor is not null)
                    Notify(supervisor.Id, NotificationType.RequestApproved, $"{r.Folio} autorizada", $"{actor.Name} autorizó la solicitud de {employee.FullName}.", r);
                var registrars = await db.Users.Where(u => u.IsActive && (u.Roles & UserRole.AdministrativeRegistrar) == UserRole.AdministrativeRegistrar)
                    .Select(u => u.EmployeeId).ToListAsync(ct);
                foreach (var id in registrars)
                    Notify(id, NotificationType.RequestSubmitted, $"{r.Folio} lista para registro", $"Solicitud autorizada de {employee.FullName} pendiente de registro administrativo.", r);
                await EmailAsync("manager-approved", policy.AdministrativeMailbox, null, r, "Solicitud autorizada para registro administrativo",
                    $"La solicitud de {employee.FullName} cuenta con las dos autorizaciones gerenciales y está lista para su registro administrativo.", actor.Name, comment, ct);
                break;
            }
            case WorkflowAction.ManagerReject:
                Notify(employee.Id, NotificationType.RequestRejected, $"{r.Folio} rechazada por jefe superior", $"{actor.Name} rechazó tu solicitud.", r);
                if (supervisor is not null)
                    Notify(supervisor.Id, NotificationType.RequestRejected, $"{r.Folio} rechazada por jefe superior", $"{actor.Name} rechazó la solicitud de {employee.FullName}.", r);
                await EmailAsync("manager-rejected", employee.Email, supervisor?.Email, r, "Solicitud rechazada por jefe superior",
                    $"{actor.Name} (jefe superior) rechazó la solicitud. La solicitud no continuará su trámite.", actor.Name, comment, ct);
                break;
            case WorkflowAction.AdministrativeObserve:
            {
                Notify(employee.Id, NotificationType.AdministrativeObservation, $"{r.Folio} con observaciones administrativas", Text.Summarize(comment, 160), r);
                var admins = await db.Users.Where(u => u.IsActive && (u.Roles & UserRole.ProductAdmin) == UserRole.ProductAdmin).Select(u => u.EmployeeId).ToListAsync(ct);
                foreach (var id in admins)
                    Notify(id, NotificationType.AdministrativeObservation, $"Observación administrativa en {r.Folio}", Text.Summarize(comment, 160), r);
                break;
            }
            case WorkflowAction.AdministrativeRegister:
                Notify(employee.Id, NotificationType.RequestRegistered, $"{r.Folio} registrada", "Tu solicitud fue registrada administrativamente.", r);
                await EmailAsync("administrative-registered", employee.Email, null, r, "Tu solicitud fue registrada",
                    "El área administrativa registró tu solicitud autorizada.", actor.Name, comment, ct);
                break;
            case WorkflowAction.Complete:
                Notify(employee.Id, NotificationType.RequestCompleted, $"{r.Folio} completada", "El trámite de tu solicitud concluyó.", r);
                await EmailAsync("completed", employee.Email, null, r, "Confirmación final de tu solicitud",
                    "El trámite de tu solicitud concluyó. Puedes descargar el formato con las constancias de autorización desde el expediente.", actor.Name, comment, ct);
                break;
            case WorkflowAction.Cancel:
                if (supervisor is not null && r.SubmittedAtUtc is not null)
                    Notify(supervisor.Id, NotificationType.RequestCancelled, $"{r.Folio} cancelada", $"{employee.FullName} canceló su solicitud.", r);
                if (manager is not null && r.Decisions.Any(d => d.Action == WorkflowAction.RouteToManager && d.RequestVersion == r.Version))
                    Notify(manager.Id, NotificationType.RequestCancelled, $"{r.Folio} cancelada", $"{employee.FullName} canceló su solicitud.", r);
                break;
        }
    }

    /// <summary>Envía en tiempo real los avisos ya confirmados en base de datos.</summary>
    public async Task FlushRealtimeAsync(CancellationToken ct)
    {
        if (_pendingRealtime.Count == 0) return;
        var items = _pendingRealtime.Select(p => (p.EmployeeId, DtoMapper.ToDto(p.Notification))).ToList();
        _pendingRealtime.Clear();
        try { await realtime.PushAsync(items, ct); }
        catch (Exception ex) { logger.LogWarning(ex, "No se pudo empujar la notificación en tiempo real; queda disponible en la campana."); }
    }

    public void DiscardRealtime() => _pendingRealtime.Clear();
}
