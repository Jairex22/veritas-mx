using System.ComponentModel.DataAnnotations;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;

namespace GPV.ProductTimeFlow.Application;

/// <summary>Resultado del cálculo de una captura válida.</summary>
public sealed record ComputedRequest(
    DateOnly StartDate, DateOnly EndDate, TimeOnly? StartTime, TimeOnly? EndTime, bool IsFullDay,
    decimal Hours, decimal Days, OvertimeCalculation? Overtime, IReadOnlyList<string> Warnings);

/// <summary>
/// Reglas de negocio de captura: cálculos, límites configurables, traslapes y saldo.
/// Se ejecutan al guardar el borrador y de nuevo al enviar (los datos del entorno pudieron cambiar).
/// </summary>
public sealed class RequestRules(ITimeFlowDbContext db, SettingsService settings, LocalClock clock)
{
    public static List<string> Annotations(object input)
    {
        var results = new List<ValidationResult>();
        Validator.TryValidateObject(input, new ValidationContext(input), results, validateAllProperties: true);
        return results.Select(r => r.ErrorMessage ?? "Dato inválido.").ToList();
    }

    public static (DateTime Start, DateTime End) Interval(RequestKind kind, DateOnly start, DateOnly end, TimeOnly? startTime, TimeOnly? endTime, bool fullDay)
    {
        if (kind == RequestKind.Overtime && startTime is not null && endTime is not null)
        {
            var calc = OvertimeCalculator.Calculate(start, startTime.Value, endTime.Value);
            return (calc.StartLocal, calc.EndLocal);
        }
        if (!fullDay && startTime is not null && endTime is not null)
            return (start.ToDateTime(startTime.Value), start.ToDateTime(endTime.Value));
        return (start.ToDateTime(TimeOnly.MinValue), end.AddDays(1).ToDateTime(TimeOnly.MinValue));
    }

    public async Task<ComputedRequest> ValidateAsync(Employee employee, RequestInput input, Guid? excludeRequestId, CancellationToken ct)
    {
        var errors = Annotations(input);
        var warnings = new List<string>();
        var policy = await settings.GetPolicyAsync(ct);
        var calendar = await settings.GetCalendarAsync(ct);
        var today = clock.Today;
        var maxFuture = today.AddDays(policy.RequestMaxDaysInFuture);

        decimal hours = 0, days = 0;
        OvertimeCalculation? ot = null;
        var start = input.StartDate;
        var end = input.EndDate ?? input.StartDate;
        TimeOnly? st = input.StartTime, et = input.EndTime;
        var fullDay = input.IsFullDay;

        if (start == default) errors.Add("Indique la fecha.");
        if (start > maxFuture) errors.Add($"La fecha no puede ser posterior a {policy.RequestMaxDaysInFuture} días.");

        switch (input.Kind)
        {
            case RequestKind.Overtime:
                fullDay = false;
                end = start;
                if (st is null || et is null) { errors.Add("Indique la hora inicial y la hora final."); break; }
                if (st == et) { errors.Add("La hora inicial y la final no pueden ser iguales."); break; }
                ot = OvertimeCalculator.Calculate(start, st.Value, et.Value);
                hours = ot.Hours;
                if (ot.CrossesMidnight) warnings.Add("El horario cruza la medianoche: termina al día siguiente.");
                if (hours < policy.OvertimeMinHours) errors.Add($"El mínimo por solicitud es {Labels.Hours(policy.OvertimeMinHours)}.");
                if (hours > policy.OvertimeMaxHoursPerRequest) errors.Add($"El máximo por solicitud es {Labels.Hours(policy.OvertimeMaxHoursPerRequest)}.");
                if (start < today.AddDays(-policy.OvertimeMaxDaysInPast)) errors.Add($"Solo se puede registrar tiempo extra de hasta {policy.OvertimeMaxDaysInPast} días anteriores.");
                if (string.IsNullOrWhiteSpace(input.Project)) errors.Add("Indique el proyecto.");
                if (string.IsNullOrWhiteSpace(input.Activity) || input.Activity.Trim().Length < 5) errors.Add("Describa la actividad realizada o planeada.");
                if (errors.Count == 0)
                {
                    var monthHours = (await db.OvertimeRecords.AsNoTracking()
                        .Where(o => o.EmployeeId == employee.Id && o.PeriodYear == start.Year && o.PeriodMonth == start.Month && o.RequestId != excludeRequestId)
                        .Join(db.Requests, o => o.RequestId, r => r.Id, (o, r) => new { o.Hours, r.Status })
                        .ToListAsync(ct))
                        .Where(x => x.Status is not (RequestStatus.Draft or RequestStatus.Cancelled or RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected))
                        .Sum(x => x.Hours);
                    if (monthHours + hours > policy.OvertimeMaxHoursPerMonth)
                        errors.Add($"Se excede el máximo mensual configurado de {Labels.Hours(policy.OvertimeMaxHoursPerMonth)} (acumulado: {Labels.Hours(monthHours)}).");
                    else if (monthHours + hours > policy.OvertimeMaxHoursPerMonth * 0.8m)
                        warnings.Add($"Acumularás {Labels.Hours(monthHours + hours)} de {Labels.Hours(policy.OvertimeMaxHoursPerMonth)} permitidas en el mes.");
                }
                break;

            case RequestKind.Vacation:
                fullDay = true; st = null; et = null;
                if (input.EndDate is null) errors.Add("Indique la fecha final.");
                if (end < start) { errors.Add("La fecha final no puede ser anterior a la inicial."); break; }
                if (start < today) errors.Add("Las vacaciones deben solicitarse para fechas a partir de hoy.");
                days = calendar.CountWorkingDays(start, end);
                if (days <= 0) errors.Add("El rango seleccionado no contiene días hábiles.");
                if (days > policy.VacationMaxConsecutiveDays) errors.Add($"El máximo de días consecutivos por solicitud es {policy.VacationMaxConsecutiveDays}.");
                if (errors.Count == 0)
                {
                    var balance = await AvailableVacationDaysAsync(employee.Id, start.Year, excludeRequestId, ct);
                    if (days > balance && !policy.VacationAllowNegativeBalance)
                        errors.Add($"Saldo insuficiente: solicitas {Labels.Days(days)} y tienes {Labels.Days(balance)} disponibles.");
                }
                break;

            case RequestKind.PaidLeave:
            case RequestKind.UnpaidLeave:
                if (string.IsNullOrWhiteSpace(input.Justification) || input.Justification.Trim().Length < 10)
                    errors.Add("La justificación es obligatoria (mínimo 10 caracteres).");
                if (start < today.AddDays(-policy.OvertimeMaxDaysInPast))
                    errors.Add($"Solo se pueden registrar permisos de hasta {policy.OvertimeMaxDaysInPast} días anteriores.");
                if (input.LeaveCategoryId is int catId)
                {
                    var cat = await db.LeaveCategories.AsNoTracking().FirstOrDefaultAsync(c => c.Id == catId, ct);
                    if (cat is null || !cat.IsActive || cat.AppliesTo != input.Kind) errors.Add("La clasificación seleccionada no es válida para este tipo de permiso.");
                }
                else errors.Add("Seleccione la clasificación del permiso.");
                if (fullDay)
                {
                    st = null; et = null;
                    if (end < start) { errors.Add("La fecha final no puede ser anterior a la inicial."); break; }
                    days = calendar.CountWorkingDays(start, end);
                    if (days <= 0) errors.Add("El rango seleccionado no contiene días hábiles.");
                }
                else
                {
                    end = start;
                    if (st is null || et is null) { errors.Add("Indique la hora inicial y la hora final del permiso parcial."); break; }
                    if (et <= st) { errors.Add("En un permiso parcial la hora final debe ser posterior a la inicial."); break; }
                    hours = Math.Round((decimal)(et.Value - st.Value).TotalMinutes / 60m, 2);
                    if (!calendar.IsWorkingDay(start)) warnings.Add("La fecha seleccionada no es día hábil.");
                }
                break;
        }

        if (errors.Count == 0)
        {
            var overlap = await FindOverlapAsync(employee.Id, input.Kind, start, end, st, et, fullDay, excludeRequestId, ct);
            if (overlap is not null) errors.Add($"Se traslapa con la solicitud {overlap.Folio} ({Labels.Kind(overlap.Kind)}, {Labels.Status(overlap.Status)}).");
        }

        if (errors.Count > 0) throw new BusinessRuleException(errors.Distinct().ToList());
        return new ComputedRequest(start, end, st, et, fullDay, hours, days, ot, warnings);
    }

    /// <summary>Detecta duplicados y traslapes con cualquier solicitud vigente del mismo empleado.</summary>
    public async Task<Request?> FindOverlapAsync(int employeeId, RequestKind kind, DateOnly start, DateOnly end, TimeOnly? st, TimeOnly? et, bool fullDay, Guid? excludeId, CancellationToken ct)
    {
        var (aStart, aEnd) = Interval(kind, start, end, st, et, fullDay);
        var fromDate = start.AddDays(-1);
        var toDate = end.AddDays(1);
        var candidates = await db.Requests.AsNoTracking().Include(r => r.Periods)
            .Where(r => r.EmployeeId == employeeId && r.Id != excludeId
                && r.Status != RequestStatus.Draft && r.Status != RequestStatus.Cancelled
                && r.Status != RequestStatus.SupervisorRejected && r.Status != RequestStatus.ManagerRejected
                && r.Periods.Any(p => p.StartDate <= toDate && p.EndDate >= fromDate))
            .ToListAsync(ct);
        foreach (var r in candidates)
        foreach (var p in r.Periods)
        {
            var (bStart, bEnd) = Interval(r.Kind, p.StartDate, p.EndDate, p.StartTime, p.EndTime, r.IsFullDay);
            if (OvertimeCalculator.Overlaps(aStart, aEnd, bStart, bEnd)) return r;
        }
        return null;
    }

    /// <summary>Saldo disponible = asignado + ajustes/reintegros − consumos − días en trámite.</summary>
    public async Task<decimal> AvailableVacationDaysAsync(int employeeId, int year, Guid? excludeRequestId, CancellationToken ct)
    {
        var balance = await db.VacationBalances.AsNoTracking().Include(b => b.Transactions)
            .FirstOrDefaultAsync(b => b.EmployeeId == employeeId && b.PeriodYear == year, ct);
        var ledger = balance is null ? 0 : balance.EntitledDays + balance.Transactions.Sum(t => t.Days);
        var pending = await PendingVacationDaysAsync(employeeId, year, excludeRequestId, ct);
        return ledger - pending;
    }

    public async Task<decimal> PendingVacationDaysAsync(int employeeId, int year, Guid? excludeRequestId, CancellationToken ct)
    {
        var start = new DateOnly(year, 1, 1);
        var end = new DateOnly(year, 12, 31);
        var pending = await db.Requests.AsNoTracking()
            .Where(r => r.EmployeeId == employeeId && r.Kind == RequestKind.Vacation && r.Id != excludeRequestId
                && (r.Status == RequestStatus.Submitted || r.Status == RequestStatus.PendingSupervisor || r.Status == RequestStatus.SupervisorApproved
                    || r.Status == RequestStatus.PendingManager || r.Status == RequestStatus.ReturnedForCorrection)
                && r.Periods.Any(p => p.StartDate >= start && p.StartDate <= end))
            .Select(r => r.TotalDays).ToListAsync(ct);
        return pending.Sum();
    }
}
