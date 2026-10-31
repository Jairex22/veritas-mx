using System.Text.Json;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;

namespace GPV.ProductTimeFlow.Application;

public sealed record FileResultDto(byte[] Content, string ContentType, string FileName);

/// <summary>Generación de expediente PDF con constancias de autorización y QR de verificación.</summary>
public sealed class DocumentService(ITimeFlowDbContext db, ActorGuard guard, IPdfRenderer pdf, IQrCodeGenerator qr, SettingsService settings,
    AuditWriter audit, LocalClock clock, EnvironmentInfo env)
{
    public async Task<FileResultDto> RequestPdfAsync(Actor actor, Guid id, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var request = await db.Requests.AsNoTracking().WithDetail().FirstOrDefaultAsync(r => r.Id == id, ct);
        if (request is null || !RequestAccess.CanView(request, actor)) throw new NotFoundException();
        var detail = DtoMapper.ToDetail(request, actor, includeSignatureImages: false);
        var policy = await settings.GetPolicyAsync(ct);
        var url = $"{env.BaseUrl}/verificar/{request.Folio}?c={request.ContentHash[..16]}";
        var images = request.Signatures.Where(s => s.IsValid && s.RequestVersion == request.Version).ToDictionary(s => s.Id, s => s.ImagePng);
        var bytes = pdf.RenderRequest(new RequestDocumentModel(detail, url, qr.Png(url), images, policy.DocumentFooterText ?? "",
            clock.LocalNow, actor.Name, clock.Zone.Id, env.Label));
        audit.Write(actor, "document.pdf_generated", nameof(Request), request.Id.ToString(), new { request.Folio, request.Version });
        await db.SaveChangesAsync(ct);
        return new FileResultDto(bytes, "application/pdf", $"{request.Folio}.pdf");
    }

    public async Task<(Attachment Meta, Stream Content)> AttachmentAsync(Actor actor, Guid attachmentId, IFileStorage storage, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var a = await db.Attachments.AsNoTracking().FirstOrDefaultAsync(x => x.Id == attachmentId && !x.IsDeleted, ct) ?? throw new NotFoundException();
        var request = await db.Requests.AsNoTracking().FirstOrDefaultAsync(r => r.Id == a.RequestId, ct);
        if (request is null || !RequestAccess.CanView(request, actor)) throw new NotFoundException();
        var stream = await storage.OpenReadAsync(a.StorageKey, ct) ?? throw new NotFoundException("El archivo no está disponible en el almacenamiento.");
        audit.Write(actor, "attachment.downloaded", nameof(Attachment), a.Id.ToString(), new { request.Folio, a.FileName });
        await db.SaveChangesAsync(ct);
        return (a, stream);
    }
}

/// <summary>
/// Exportación a Excel para el trámite administrativo. Restringida por rol, trazable (bitácora ExcelExports)
/// y de solo lectura: nunca modifica solicitudes.
/// </summary>
public sealed class ExportService(ITimeFlowDbContext db, ActorGuard guard, IExcelExporter excel, AuditWriter audit, LocalClock clock, EnvironmentInfo env)
{
    public async Task<FileResultDto> ExportAsync(Actor actor, ExportFilter filter, CancellationToken ct = default)
    {
        var employee = await guard.RequireActiveAsync(actor, ct);
        var roles = employee.User!.Roles;
        if (!roles.HasFlag(UserRole.ProductAdmin) && !roles.HasFlag(UserRole.AdministrativeRegistrar)
            && !roles.HasFlag(UserRole.SeniorManager) && !roles.HasFlag(UserRole.DirectSupervisor))
            throw new ForbiddenException("Su rol no permite exportar información.");
        if (filter.From is DateOnly f && filter.To is DateOnly t && t < f) throw new BusinessRuleException("El periodo es inválido.");

        var q = db.Requests.AsNoTracking().VisibleTo(actor).Where(r => r.Status != RequestStatus.Draft);
        // Jefas y jefes solo exportan solicitudes de su equipo; RH y Producto, las que ya alcanzaron la etapa administrativa o todas.
        if (!roles.HasFlag(UserRole.ProductAdmin) && !roles.HasFlag(UserRole.AdministrativeRegistrar))
            q = q.Where(r => r.AssignedSupervisorId == actor.EmployeeId || r.AssignedManagerId == actor.EmployeeId);
        q = filter.Set switch
        {
            "processed" => q.Where(r => r.Status == RequestStatus.AdministrativeRegistered || r.Status == RequestStatus.Completed),
            "all" => q,
            _ => q.Where(r => r.Status == RequestStatus.ManagerApproved || r.Status == RequestStatus.PendingAdministrativeRegistration
                           || r.Status == RequestStatus.AdministrativeObserved || r.Status == RequestStatus.AdministrativeRegistered || r.Status == RequestStatus.Completed)
        };
        if (filter.Kind is RequestKind k) q = q.Where(r => r.Kind == k);
        if (filter.EmployeeId is int e) q = q.Where(r => r.EmployeeId == e);
        if (filter.From is DateOnly from) q = q.Where(r => r.Periods.Any(p => p.EndDate >= from));
        if (filter.To is DateOnly to) q = q.Where(r => r.Periods.Any(p => p.StartDate <= to));

        var requests = await q.OrderBy(r => r.Folio).Take(20000)
            .Include(r => r.Employee).ThenInclude(x => x!.Department).Include(r => r.Periods).Include(r => r.AssignedSupervisor).Include(r => r.AssignedManager)
            .Include(r => r.Decisions).Include(r => r.Administrative).AsSplitQuery().ToListAsync(ct);

        DateTime? Local(DateTime? utc) => utc is null ? null : clock.ToLocal(utc.Value);
        var rows = requests.Select(r =>
        {
            var p = r.PrimaryPeriod!;
            var sup = r.Decisions.Where(d => d.Action == WorkflowAction.SupervisorApprove && d.RequestVersion == r.Version).OrderByDescending(d => d.OccurredAtUtc).FirstOrDefault();
            var mgr = r.Decisions.Where(d => d.Action == WorkflowAction.ManagerApprove && d.RequestVersion == r.Version).OrderByDescending(d => d.OccurredAtUtc).FirstOrDefault();
            var obs = string.Join(" | ", new[] { r.Observations, r.Administrative?.Observations }.Where(x => !string.IsNullOrWhiteSpace(x)));
            return new ExportRow(r.Folio, clock.ToLocal(r.CreatedAtUtc), r.Employee!.EmployeeNumber, r.Employee.FullName, r.Employee.Department?.Name ?? "",
                r.Employee.Area ?? "", Labels.Kind(r.Kind), p.StartDate, p.EndDate, r.TotalHours, r.TotalDays, r.Reason,
                r.AssignedSupervisor?.FullName, Local(sup?.OccurredAtUtc), r.AssignedManager?.FullName, Local(mgr?.OccurredAtUtc),
                Labels.Status(r.Status), Local(r.Administrative?.RegisteredAtUtc), obs, r.Id);
        }).ToList();

        var filterText = JsonSerializer.Serialize(new { filter.Set, Kind = filter.Kind?.ToString(), filter.EmployeeId, From = filter.From?.ToString("yyyy-MM-dd"), To = filter.To?.ToString("yyyy-MM-dd") });
        var bytes = excel.ExportRequests(rows, new ExportMetadata(actor.Name, clock.LocalNow, filterText, env.Label, clock.Zone.Id));
        var fileName = $"TimeFlow_{filter.Set}_{clock.LocalNow:yyyyMMdd_HHmm}.xlsx";
        var log = new ExcelExport
        {
            Id = Guid.NewGuid(), ExportedByEmployeeId = actor.EmployeeId, ExportedByName = actor.Name, ExportedAtUtc = clock.UtcNow,
            FileName = fileName, Filters = filterText, RowCount = rows.Count, Sha256 = RequestContentHasher.Sha256Hex(bytes)
        };
        db.ExcelExports.Add(log);
        audit.Write(actor, "export.excel", nameof(ExcelExport), log.Id.ToString(), new { rows = rows.Count, filterText, log.Sha256 });
        await db.SaveChangesAsync(ct);
        return new FileResultDto(bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", fileName);
    }

    public async Task<IReadOnlyList<ExcelExportLogDto>> HistoryAsync(Actor actor, CancellationToken ct = default)
    {
        var e = await guard.RequireActiveAsync(actor, ct);
        var q = db.ExcelExports.AsNoTracking();
        if (!e.User!.Roles.HasFlag(UserRole.ProductAdmin)) q = q.Where(x => x.ExportedByEmployeeId == actor.EmployeeId);
        return await q.OrderByDescending(x => x.ExportedAtUtc).Take(100)
            .Select(x => new ExcelExportLogDto(x.Id, x.ExportedAtUtc, x.ExportedByName, x.FileName, x.RowCount, x.Filters, x.Sha256)).ToListAsync(ct);
    }

    public FileResultDto ImportTemplate() => new(excel.EmployeeImportTemplate(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "Plantilla_Importacion_Empleados.xlsx");
}

public enum LoginOutcome { Success, InvalidCredentials, LockedOut, Disabled }

public sealed record LoginResult(LoginOutcome Outcome, int? EmployeeId, UserRole Roles, string? Name, Guid SecurityStamp)
{
    public string Message => Outcome switch
    {
        LoginOutcome.Success => "Acceso concedido.",
        LoginOutcome.LockedOut => "La cuenta está bloqueada temporalmente por intentos fallidos. Intente más tarde o contacte al administrador.",
        _ => "Correo o contraseña incorrectos."
    };
}

/// <summary>
/// Autenticación local para DEMO/TEST con protección contra fuerza bruta (bloqueo tras 5 intentos durante 15 minutos).
/// En producción la autenticación la realiza Microsoft Entra ID y este servicio solo vincula la identidad.
/// </summary>
public sealed class AuthService(ITimeFlowDbContext db, IPasswordService passwords, AuditWriter audit, LocalClock clock)
{
    public const int MaxFailedAttempts = 5;
    public static readonly TimeSpan LockoutDuration = TimeSpan.FromMinutes(15);

    public async Task<LoginResult> ValidateAsync(string email, string password, string? ip, CancellationToken ct = default)
    {
        var normalized = (email ?? "").Trim().ToLowerInvariant();
        var employee = await db.Employees.Include(e => e.User).FirstOrDefaultAsync(e => e.NormalizedEmail == normalized, ct);
        var user = employee?.User;
        var now = clock.UtcNow;
        if (user is null || user.PasswordHash is null)
        {
            // Mismo costo computacional para no revelar si la cuenta existe.
            passwords.Verify("AQAAAAIAAYagAAAAEFakeHashForTimingEqualizationOnly0000000000000000==", password ?? "");
            audit.Write(new Actor(0, "Anónimo", UserRole.None, ip), "auth.login_failed", nameof(UserAccount), "unknown", new { reason = "unknown_or_external" });
            await db.SaveChangesAsync(ct);
            return new LoginResult(LoginOutcome.InvalidCredentials, null, UserRole.None, null, Guid.Empty);
        }
        var actor = new Actor(employee!.Id, employee.FullName, user.Roles, ip);
        if (user.LockoutEndUtc > now)
        {
            audit.Write(actor, "auth.login_locked", nameof(UserAccount), employee.Id.ToString());
            await db.SaveChangesAsync(ct);
            return new LoginResult(LoginOutcome.LockedOut, null, UserRole.None, null, Guid.Empty);
        }
        if (!passwords.Verify(user.PasswordHash, password ?? ""))
        {
            // Actualización atómica en la base (sin token de concurrencia): intentos simultáneos se cuentan todos y nunca producen error 500.
            var userId = user.Id;
            await db.Users.Where(u => u.Id == userId).ExecuteUpdateAsync(s => s.SetProperty(u => u.FailedLoginCount, u => u.FailedLoginCount + 1), ct);
            var lockUntil = now.Add(LockoutDuration);
            var locked = await db.Users.Where(u => u.Id == userId && u.FailedLoginCount >= MaxFailedAttempts)
                .ExecuteUpdateAsync(s => s.SetProperty(u => u.LockoutEndUtc, lockUntil).SetProperty(u => u.FailedLoginCount, 0), ct) > 0;
            audit.Write(actor, "auth.login_failed", nameof(UserAccount), employee.Id.ToString(), new { locked });
            await db.SaveChangesAsync(ct);
            return new LoginResult(locked ? LoginOutcome.LockedOut : LoginOutcome.InvalidCredentials, null, UserRole.None, null, Guid.Empty);
        }
        if (!user.IsActive || !employee.IsActive)
        {
            audit.Write(actor, "auth.login_disabled", nameof(UserAccount), employee.Id.ToString());
            await db.SaveChangesAsync(ct);
            return new LoginResult(LoginOutcome.Disabled, null, UserRole.None, null, Guid.Empty);
        }
        var id = user.Id;
        await db.Users.Where(u => u.Id == id).ExecuteUpdateAsync(s => s
            .SetProperty(u => u.FailedLoginCount, 0).SetProperty(u => u.LockoutEndUtc, (DateTime?)null).SetProperty(u => u.LastLoginUtc, now), ct);
        audit.Write(actor, "auth.login_success", nameof(UserAccount), employee.Id.ToString());
        await db.SaveChangesAsync(ct);
        return new LoginResult(LoginOutcome.Success, employee.Id, user.Roles, employee.FullName, user.SecurityStamp);
    }

    /// <summary>Vincula una identidad de Microsoft Entra ID (por objectId o correo corporativo) con el empleado.</summary>
    public async Task<LoginResult> ResolveExternalAsync(string? objectId, string? email, CancellationToken ct = default)
    {
        var normalized = (email ?? "").Trim().ToLowerInvariant();
        var employee = await db.Employees.Include(e => e.User)
            .FirstOrDefaultAsync(e => (objectId != null && e.User!.ExternalObjectId == objectId) || e.NormalizedEmail == normalized, ct);
        if (employee?.User is null || !employee.IsActive || !employee.User.IsActive)
            return new LoginResult(LoginOutcome.Disabled, null, UserRole.None, null, Guid.Empty);
        var uid = employee.User.Id;
        var now = clock.UtcNow;
        if (objectId is not null && employee.User.ExternalObjectId is null)
            await db.Users.Where(u => u.Id == uid && u.ExternalObjectId == null).ExecuteUpdateAsync(s => s.SetProperty(u => u.ExternalObjectId, objectId), ct);
        await db.Users.Where(u => u.Id == uid).ExecuteUpdateAsync(s => s.SetProperty(u => u.LastLoginUtc, now), ct);
        audit.Write(new Actor(employee.Id, employee.FullName, employee.User.Roles), "auth.external_login", nameof(UserAccount), employee.Id.ToString());
        await db.SaveChangesAsync(ct);
        return new LoginResult(LoginOutcome.Success, employee.Id, employee.User.Roles, employee.FullName, employee.User.SecurityStamp);
    }

    /// <summary>Revalida en cada solicitud que la sesión sigue vigente (roles y estado no cambiaron).</summary>
    public async Task<bool> IsSessionValidAsync(int employeeId, Guid securityStamp, CancellationToken ct = default) =>
        await db.Users.AsNoTracking().AnyAsync(u => u.EmployeeId == employeeId && u.IsActive && u.SecurityStamp == securityStamp && u.Employee!.IsActive, ct);

    public async Task<UserRole> CurrentRolesAsync(int employeeId, CancellationToken ct = default) =>
        await db.Users.AsNoTracking().Where(u => u.EmployeeId == employeeId).Select(u => u.Roles).FirstOrDefaultAsync(ct);
}

public sealed record IntegrationStatus(string EmailProvider, string AuthenticationMode);

public sealed class HealthService(ITimeFlowDbContext db, ActorGuard guard, EnvironmentInfo env, IntegrationStatus integrations, LocalClock clock)
{
    public async Task<SystemHealthDto> GetAsync(Actor actor, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var reachable = await db.Database.CanConnectAsync(ct);
        return new SystemHealthDto(env.Label, db.ProviderName, reachable, integrations.EmailProvider, integrations.AuthenticationMode,
            await db.EmailOutbox.CountAsync(m => m.Status == EmailStatus.Pending, ct),
            await db.EmailOutbox.CountAsync(m => m.Status == EmailStatus.Failed, ct),
            await db.AuditLogs.LongCountAsync(ct),
            typeof(HealthService).Assembly.GetName().Version?.ToString(3) ?? "4.0.0",
            clock.UtcNow, clock.Zone.Id, Environment.WorkingSet / (1024 * 1024));
    }
}

/// <summary>Genera recordatorios de solicitudes pendientes (una vez por día y por paso).</summary>
public sealed class ReminderService(ITimeFlowDbContext db, SettingsService settings, NotificationDispatcher notifications, LocalClock clock)
{
    public async Task<int> EnqueueRemindersAsync(CancellationToken ct = default)
    {
        var policy = await settings.GetPolicyAsync(ct);
        var threshold = clock.UtcNow.AddHours(-policy.ReminderAfterHours);
        var day = clock.Today.ToString("yyyyMMdd");
        var stale = await db.Requests.Include(r => r.Employee).Include(r => r.Periods).Include(r => r.AssignedSupervisor).Include(r => r.AssignedManager)
            .Where(r => (r.Status == RequestStatus.PendingSupervisor || r.Status == RequestStatus.PendingManager || r.Status == RequestStatus.PendingAdministrativeRegistration)
                && r.StatusChangedAtUtc < threshold)
            .Take(500).ToListAsync(ct);
        var count = 0;
        foreach (var r in stale)
        {
            var key = $"reminder:{r.Id:N}:{r.Status}:{day}";
            if (await db.Notifications.AnyAsync(n => n.DeduplicationKey == key, ct)) continue;
            var assignee = r.Status switch { RequestStatus.PendingSupervisor => r.AssignedSupervisor, RequestStatus.PendingManager => r.AssignedManager, _ => null };
            if (assignee is not null)
            {
                notifications.Notify(assignee.Id, NotificationType.PendingReminder, $"Recordatorio: {r.Folio} pendiente", $"La solicitud de {r.Employee?.FullName} espera tu decisión.", r, key);
                await notifications.EmailAsync("reminder", assignee.Email, null, r, "Recordatorio de solicitud pendiente",
                    $"La solicitud de {r.Employee?.FullName} lleva más de {policy.ReminderAfterHours} horas esperando tu decisión.", assignee.FullName, null, ct, $":{day}");
            }
            else
            {
                await notifications.EmailAsync("reminder-admin", policy.AdministrativeMailbox, null, r, "Recordatorio: solicitud pendiente de registro",
                    "Hay una solicitud autorizada pendiente de registro administrativo.", null, null, ct, $":{day}");
                db.Notifications.Add(new Notification { Id = Guid.NewGuid(), RecipientEmployeeId = r.EmployeeId, Type = NotificationType.PendingReminder, Title = "", Message = "", CreatedAtUtc = clock.UtcNow, ReadAtUtc = clock.UtcNow, DeduplicationKey = key });
            }
            count++;
        }
        await db.SaveChangesAsync(ct);
        await notifications.FlushRealtimeAsync(ct);
        return count;
    }
}
