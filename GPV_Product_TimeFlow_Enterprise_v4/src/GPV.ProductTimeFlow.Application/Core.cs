using System.Globalization;
using System.Reflection;
using System.Text.Json;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace GPV.ProductTimeFlow.Application;

/// <summary>Parámetros de política almacenados en SystemSettings (clave "Policy.*").</summary>
public sealed class SettingsService(ITimeFlowDbContext db, LocalClock clock)
{
    private const string Prefix = "Policy.";
    private PolicySettingsDto? _cache;

    public async Task<PolicySettingsDto> GetPolicyAsync(CancellationToken ct = default)
    {
        if (_cache is not null) return _cache;
        var values = await db.SystemSettings.AsNoTracking().Where(s => s.Key.StartsWith(Prefix)).ToDictionaryAsync(s => s.Key, s => s.Value, ct);
        var dto = new PolicySettingsDto();
        foreach (var prop in typeof(PolicySettingsDto).GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            if (!values.TryGetValue(Prefix + prop.Name, out var raw)) continue;
            try
            {
                var target = Nullable.GetUnderlyingType(prop.PropertyType) ?? prop.PropertyType;
                prop.SetValue(dto, raw.Length == 0 && target != typeof(string) ? null : Convert.ChangeType(raw, target, CultureInfo.InvariantCulture));
            }
            catch (FormatException) { /* valor inválido: se conserva el valor por defecto */ }
        }
        return _cache = dto;
    }

    public async Task<WorkCalendar> GetCalendarAsync(CancellationToken ct = default)
    {
        var policy = await GetPolicyAsync(ct);
        var holidays = await db.Holidays.AsNoTracking().Where(h => h.IsActive).Select(h => new { h.Date, h.Name }).ToListAsync(ct);
        return new WorkCalendar(WorkCalendar.ParseWorkingDays(policy.WorkingDays), holidays.Select(h => (h.Date, h.Name)));
    }

    internal async Task SavePolicyAsync(PolicySettingsDto dto, string updatedBy, CancellationToken ct)
    {
        var existing = await db.SystemSettings.Where(s => s.Key.StartsWith(Prefix)).ToDictionaryAsync(s => s.Key, ct);
        foreach (var prop in typeof(PolicySettingsDto).GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            var key = Prefix + prop.Name;
            var value = Convert.ToString(prop.GetValue(dto), CultureInfo.InvariantCulture) ?? "";
            if (!existing.TryGetValue(key, out var setting))
            {
                setting = new SystemSetting { Key = key, Description = prop.Name };
                db.SystemSettings.Add(setting);
            }
            setting.Value = value;
            setting.UpdatedAtUtc = clock.UtcNow;
            setting.UpdatedByName = updatedBy;
        }
        _cache = null;
    }
}

/// <summary>Registra eventos de auditoría. El encadenamiento por hash se calcula al guardar (Infrastructure).</summary>
public sealed class AuditWriter(ITimeFlowDbContext db, LocalClock clock)
{
    public void Write(Actor actor, string action, string entityType, string entityId, object? details = null)
    {
        db.AuditLogs.Add(new AuditLog
        {
            OccurredAtUtc = clock.UtcNow,
            ActorEmployeeId = actor.EmployeeId == 0 ? null : actor.EmployeeId,
            ActorName = actor.Name,
            Action = action,
            EntityType = entityType,
            EntityId = entityId,
            Details = details is null ? null : details as string ?? JsonSerializer.Serialize(details),
            IpAddress = actor.IpAddress
        });
    }
}

/// <summary>Paso 1 de toda acción: validar que la identidad existe, está activa y conserva los roles declarados.</summary>
public sealed class ActorGuard(ITimeFlowDbContext db)
{
    public async Task<Employee> RequireActiveAsync(Actor actor, CancellationToken ct)
    {
        var employee = await db.Employees.Include(e => e.User)
            .FirstOrDefaultAsync(e => e.Id == actor.EmployeeId, ct);
        if (employee is null || !employee.IsActive || employee.User is null || !employee.User.IsActive)
            throw new ForbiddenException("Su cuenta no está activa. Contacte al administrador de Producto.");
        return employee;
    }

    public async Task<Employee> RequireRoleAsync(Actor actor, UserRole role, CancellationToken ct)
    {
        var employee = await RequireActiveAsync(actor, ct);
        if ((employee.User!.Roles & role) != role) throw new ForbiddenException();
        return employee;
    }
}

/// <summary>Autorización basada en recursos para solicitudes.</summary>
public static class RequestAccess
{
    private static readonly RequestStatus[] AdministrativeStatuses =
    [
        RequestStatus.PendingAdministrativeRegistration, RequestStatus.AdministrativeObserved,
        RequestStatus.AdministrativeRegistered, RequestStatus.Completed
    ];

    public static bool IsAdministrativeStage(RequestStatus status) => AdministrativeStatuses.Contains(status);

    /// <summary>Filtro de consulta: solo solicitudes visibles para el actor.</summary>
    public static IQueryable<Request> VisibleTo(this IQueryable<Request> query, Actor actor)
    {
        if (actor.Has(UserRole.ProductAdmin)) return query;
        var id = actor.EmployeeId;
        var registrar = actor.Has(UserRole.AdministrativeRegistrar);
        return query.Where(r => r.EmployeeId == id
            || (r.Status != RequestStatus.Draft && (r.AssignedSupervisorId == id || r.AssignedManagerId == id))
            || (registrar && AdministrativeStatuses.Contains(r.Status)));
    }

    public static bool CanView(Request r, Actor actor) =>
        actor.Has(UserRole.ProductAdmin)
        || r.EmployeeId == actor.EmployeeId
        || (r.Status != RequestStatus.Draft && (r.AssignedSupervisorId == actor.EmployeeId || r.AssignedManagerId == actor.EmployeeId))
        || (actor.Has(UserRole.AdministrativeRegistrar) && IsAdministrativeStage(r.Status));

    public static RequestPermissionsDto Permissions(Request r, Actor actor)
    {
        var owner = r.EmployeeId == actor.EmployeeId;
        var registrar = actor.Has(UserRole.AdministrativeRegistrar);
        ApprovalStepType? step = null;
        if (r.Status == RequestStatus.PendingSupervisor && r.AssignedSupervisorId == actor.EmployeeId && !owner) step = ApprovalStepType.DirectSupervisor;
        if (r.Status == RequestStatus.PendingManager && r.AssignedManagerId == actor.EmployeeId && !owner) step = ApprovalStepType.SeniorManager;
        return new RequestPermissionsDto
        {
            CanEdit = owner && r.IsEditable,
            CanSubmit = owner && RequestStateMachine.CanApply(r.Status, WorkflowAction.Submit),
            CanCancel = owner && RequestStateMachine.CanApply(r.Status, WorkflowAction.Cancel),
            CanUploadAttachments = owner && r.IsEditable,
            CanDecide = step is not null,
            DecisionStep = step,
            CanAdminReceive = registrar && r.Status == RequestStatus.PendingAdministrativeRegistration && r.Administrative?.ReceivedAtUtc is null,
            CanAdminObserve = registrar && RequestStateMachine.CanApply(r.Status, WorkflowAction.AdministrativeObserve),
            CanAdminRegister = registrar && RequestStateMachine.CanApply(r.Status, WorkflowAction.AdministrativeRegister),
            CanAdminComplete = registrar && RequestStateMachine.CanApply(r.Status, WorkflowAction.Complete),
        };
    }
}

/// <summary>Consultas reutilizables de jerarquía.</summary>
public static class HierarchyQueries
{
    public static async Task<ReportingHierarchy?> CurrentAsync(this ITimeFlowDbContext db, int employeeId, CancellationToken ct) =>
        await db.ReportingHierarchy.Include(h => h.DirectSupervisor).Include(h => h.SeniorManager)
            .Where(h => h.EmployeeId == employeeId && h.IsCurrent).OrderByDescending(h => h.EffectiveFrom).FirstOrDefaultAsync(ct);

    /// <summary>Empleados cuyo jefe directo o superior vigente es <paramref name="leaderId"/>.</summary>
    public static IQueryable<int> TeamMemberIds(this ITimeFlowDbContext db, int leaderId) =>
        db.ReportingHierarchy.Where(h => h.IsCurrent && (h.DirectSupervisorId == leaderId || h.SeniorManagerId == leaderId)).Select(h => h.EmployeeId);
}

public static class Text
{
    public static string Summarize(string? value, int max = 140)
    {
        if (string.IsNullOrWhiteSpace(value)) return "";
        var v = value.Trim().ReplaceLineEndings(" ");
        return v.Length <= max ? v : v[..(max - 1)].TrimEnd() + "…";
    }

    public static string? Clean(string? value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    public static string DateRange(DateOnly start, DateOnly end, TimeOnly? startTime = null, TimeOnly? endTime = null)
    {
        var es = CultureInfo.GetCultureInfo("es-MX");
        var s = start.ToString("dd MMM yyyy", es);
        if (startTime is not null && endTime is not null)
            return $"{s}, {startTime:HH\\:mm} – {endTime:HH\\:mm}" + (endTime <= startTime ? " (día siguiente)" : "");
        return start == end ? s : $"{s} al {end.ToString("dd MMM yyyy", es)}";
    }

    public static string Duration(RequestKind kind, decimal hours, decimal days, bool fullDay) =>
        kind == RequestKind.Overtime || (!fullDay && kind is RequestKind.PaidLeave or RequestKind.UnpaidLeave)
            ? Labels.Hours(hours) : Labels.Days(days);
}

public sealed class EnvironmentInfo(IOptions<TimeFlowOptions> options)
{
    public EnvironmentMode Mode => options.Value.Mode;
    public string Label => Mode switch
    {
        EnvironmentMode.Demo => "DEMO · datos sintéticos",
        EnvironmentMode.Test => "PRUEBAS",
        _ => "PRODUCCIÓN"
    };
    public string BaseUrl => options.Value.PublicBaseUrl.TrimEnd('/');
}
