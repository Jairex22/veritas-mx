using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;

namespace GPV.ProductTimeFlow.Application;

public sealed class RequestQueryService(ITimeFlowDbContext db, ActorGuard guard, SettingsService settings, LocalClock clock, EnvironmentInfo env)
{
    public async Task<RequestDetailDto> GetDetailAsync(Actor actor, Guid id, bool includeSignatureImages = true, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var request = await db.Requests.AsNoTracking().WithDetail().FirstOrDefaultAsync(r => r.Id == id, ct);
        if (request is null || !RequestAccess.CanView(request, actor)) throw new NotFoundException();
        return DtoMapper.ToDetail(request, actor, includeSignatureImages);
    }

    /// <summary>Obtiene los datos capturados para edición (solo el solicitante).</summary>
    public async Task<RequestInput> GetInputAsync(Actor actor, Guid id, CancellationToken ct = default)
    {
        var r = await db.Requests.AsNoTracking().Include(x => x.Periods).Include(x => x.Overtime).FirstOrDefaultAsync(x => x.Id == id, ct);
        if (r is null || r.EmployeeId != actor.EmployeeId) throw new NotFoundException();
        var p = r.PrimaryPeriod!;
        return new RequestInput
        {
            Kind = r.Kind, StartDate = p.StartDate, EndDate = p.EndDate, StartTime = p.StartTime, EndTime = p.EndTime, IsFullDay = r.IsFullDay,
            Reason = r.Reason, Justification = r.Justification, Observations = r.Observations, LeaveCategoryId = r.LeaveCategoryId,
            Project = r.Overtime?.Project, Activity = r.Overtime?.Activity
        };
    }

    public async Task<PagedResult<RequestSummaryDto>> ListAsync(Actor actor, RequestQuery query, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var policy = await settings.GetPolicyAsync(ct);
        var id = actor.EmployeeId;
        var q = db.Requests.AsNoTracking().VisibleTo(actor);
        q = query.Scope switch
        {
            RequestScope.Mine => q.Where(r => r.EmployeeId == id),
            RequestScope.ApprovalInbox => q.Where(r => (r.Status == RequestStatus.PendingSupervisor && r.AssignedSupervisorId == id)
                                                  || (r.Status == RequestStatus.PendingManager && r.AssignedManagerId == id)),
            RequestScope.TeamHistory => q.Where(r => r.Status != RequestStatus.Draft && r.EmployeeId != id && (r.AssignedSupervisorId == id || r.AssignedManagerId == id)),
            RequestScope.Administrative => actor.Has(UserRole.AdministrativeRegistrar) || actor.Has(UserRole.ProductAdmin)
                ? q.Where(r => r.Status == RequestStatus.PendingAdministrativeRegistration || r.Status == RequestStatus.AdministrativeObserved
                            || r.Status == RequestStatus.AdministrativeRegistered || r.Status == RequestStatus.Completed)
                : throw new ForbiddenException(),
            RequestScope.All => actor.Has(UserRole.ProductAdmin) ? q.Where(r => r.Status != RequestStatus.Draft || r.EmployeeId == id) : throw new ForbiddenException(),
            _ => q.Where(r => r.EmployeeId == id)
        };
        if (query.Status is RequestStatus s) q = q.Where(r => r.Status == s);
        if (query.Kind is RequestKind k) q = q.Where(r => r.Kind == k);
        if (query.EmployeeId is int e) q = q.Where(r => r.EmployeeId == e);
        if (query.From is DateOnly from) q = q.Where(r => r.Periods.Any(p => p.EndDate >= from));
        if (query.To is DateOnly to) q = q.Where(r => r.Periods.Any(p => p.StartDate <= to));
        q = query.Bucket switch
        {
            "open" => q.Where(r => r.Status == RequestStatus.Submitted || r.Status == RequestStatus.PendingSupervisor || r.Status == RequestStatus.SupervisorApproved
                                || r.Status == RequestStatus.PendingManager || r.Status == RequestStatus.ReturnedForCorrection),
            "approved" => q.Where(r => r.Status == RequestStatus.ManagerApproved || r.Status == RequestStatus.PendingAdministrativeRegistration
                                || r.Status == RequestStatus.AdministrativeObserved || r.Status == RequestStatus.AdministrativeRegistered || r.Status == RequestStatus.Completed),
            "rejected" => q.Where(r => r.Status == RequestStatus.SupervisorRejected || r.Status == RequestStatus.ManagerRejected),
            "drafts" => q.Where(r => r.Status == RequestStatus.Draft),
            "returned" => q.Where(r => r.Status == RequestStatus.ReturnedForCorrection),
            _ => q
        };
        if (!string.IsNullOrWhiteSpace(query.Search))
        {
            var term = query.Search.Trim().ToLower();
            q = q.Where(r => r.Folio.ToLower().Contains(term) || r.Employee!.FullName.ToLower().Contains(term)
                          || r.Employee.EmployeeNumber.ToLower().Contains(term) || r.Reason.ToLower().Contains(term));
        }

        var total = await q.CountAsync(ct);
        var pageSize = Math.Clamp(query.PageSize, 1, 100);
        var page = Math.Max(1, query.Page);
        var ordered = query.Scope is RequestScope.ApprovalInbox or RequestScope.Administrative
            ? q.OrderBy(r => r.StatusChangedAtUtc)
            : q.OrderByDescending(r => r.CreatedAtUtc);
        var items = await ordered.Skip((page - 1) * pageSize).Take(pageSize).WithSummary().ToListAsync(ct);
        var now = clock.UtcNow;
        return new PagedResult<RequestSummaryDto>(items.Select(r => DtoMapper.ToSummary(r, policy.UrgentAfterHours, now)).ToList(), page, pageSize, total);
    }

    public async Task<UserProfileDto> GetProfileAsync(int employeeId, CancellationToken ct = default)
    {
        var e = await db.Employees.AsNoTracking().Include(x => x.User).Include(x => x.Department).Include(x => x.Position)
            .FirstOrDefaultAsync(x => x.Id == employeeId, ct) ?? throw new NotFoundException();
        var h = await db.CurrentAsync(employeeId, ct);
        var roles = e.User?.Roles ?? UserRole.None;
        return new UserProfileDto
        {
            EmployeeId = e.Id, EmployeeNumber = e.EmployeeNumber, FullName = e.FullName, FirstName = e.FirstName, Email = e.Email,
            Roles = roles, RoleLabels = Labels.Roles(roles).ToList(), Department = e.Department?.Name, Area = e.Area, Position = e.Position?.Name,
            SupervisorName = h?.DirectSupervisor?.FullName, ManagerName = h?.SeniorManager?.FullName, EnvironmentMode = env.Mode.ToString()
        };
    }

    public async Task<DashboardDto> GetDashboardAsync(Actor actor, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var policy = await settings.GetPolicyAsync(ct);
        var profile = await GetProfileAsync(actor.EmployeeId, ct);
        var id = actor.EmployeeId;
        var now = clock.UtcNow;
        var today = clock.Today;

        var mine = await db.Requests.AsNoTracking().Where(r => r.EmployeeId == id)
            .Select(r => new { r.Status, r.Kind, r.TotalHours, r.Periods.First().StartDate }).ToListAsync(ct);
        var recent = await db.Requests.AsNoTracking().Where(r => r.EmployeeId == id).OrderByDescending(r => r.UpdatedAtUtc).Take(6).WithSummary().ToListAsync(ct);
        var available = await new RequestRules(db, settings, clock).AvailableVacationDaysAsync(id, today.Year, null, ct);
        var pendingVac = await new RequestRules(db, settings, clock).PendingVacationDaysAsync(id, today.Year, null, ct);
        var otMonth = mine.Where(r => r.Kind == RequestKind.Overtime && r.StartDate.Year == today.Year && r.StartDate.Month == today.Month);
        var unread = await db.Notifications.CountAsync(n => n.RecipientEmployeeId == id && n.ReadAtUtc == null, ct);

        var dto = new DashboardDto
        {
            Profile = profile,
            MyDrafts = mine.Count(r => r.Status == RequestStatus.Draft),
            MyInProgress = mine.Count(r => r.Status is RequestStatus.Submitted or RequestStatus.PendingSupervisor or RequestStatus.SupervisorApproved or RequestStatus.PendingManager),
            MyReturned = mine.Count(r => r.Status == RequestStatus.ReturnedForCorrection),
            MyApproved = mine.Count(r => r.Status is RequestStatus.ManagerApproved or RequestStatus.PendingAdministrativeRegistration or RequestStatus.AdministrativeObserved or RequestStatus.AdministrativeRegistered or RequestStatus.Completed),
            MyRejected = mine.Count(r => r.Status is RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected),
            VacationAvailable = available,
            VacationPending = pendingVac,
            OvertimeMonthHours = otMonth.Where(r => r.Status is not (RequestStatus.Draft or RequestStatus.Cancelled or RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected)).Sum(r => r.TotalHours),
            OvertimeMonthApprovedHours = otMonth.Where(r => r.Status is RequestStatus.ManagerApproved or RequestStatus.PendingAdministrativeRegistration or RequestStatus.AdministrativeObserved or RequestStatus.AdministrativeRegistered or RequestStatus.Completed).Sum(r => r.TotalHours),
            MyRecent = recent.Select(r => DtoMapper.ToSummary(r, policy.UrgentAfterHours, now)).ToList(),
            UnreadNotifications = unread
        };

        if (actor.Has(UserRole.DirectSupervisor) || actor.Has(UserRole.SeniorManager))
        {
            var queue = await db.Requests.AsNoTracking()
                .Where(r => (r.Status == RequestStatus.PendingSupervisor && r.AssignedSupervisorId == id) || (r.Status == RequestStatus.PendingManager && r.AssignedManagerId == id))
                .OrderBy(r => r.StatusChangedAtUtc).Take(50).WithSummary().ToListAsync(ct);
            var queueDtos = queue.Select(r => DtoMapper.ToSummary(r, policy.UrgentAfterHours, now)).ToList();
            var teamIds = await db.TeamMemberIds(id).ToListAsync(ct);
            var monthStart = new DateTime(now.Year, now.Month, 1, 0, 0, 0, DateTimeKind.Utc);
            var decisions = await db.ApprovalDecisions.AsNoTracking().CountAsync(d => d.ActorEmployeeId == id && d.OccurredAtUtc >= monthStart
                && (d.Action == WorkflowAction.SupervisorApprove || d.Action == WorkflowAction.SupervisorReject || d.Action == WorkflowAction.SupervisorReturn
                    || d.Action == WorkflowAction.ManagerApprove || d.Action == WorkflowAction.ManagerReject || d.Action == WorkflowAction.ManagerReturn), ct);
            var teamRequests = await db.Requests.AsNoTracking()
                .Where(r => r.Status != RequestStatus.Draft && (r.AssignedSupervisorId == id || r.AssignedManagerId == id))
                .Select(r => new { r.Kind, r.Status, r.TotalHours, r.Periods.First().StartDate }).ToListAsync(ct);
            var sixMonths = Enumerable.Range(0, 6).Select(i => today.AddMonths(-5 + i)).ToList();
            var es = System.Globalization.CultureInfo.GetCultureInfo("es-MX");
            var upcoming = await GetCalendarAsync(actor, today, today.AddDays(30), actor.Has(UserRole.SeniorManager) ? CalendarScope.Department : CalendarScope.Team, ct);

            dto = dto with
            {
                ApprovalQueue = queueDtos,
                ApprovalsPending = queueDtos.Count,
                ApprovalsUrgent = queueDtos.Count(q => q.IsUrgent),
                TeamSize = teamIds.Count,
                DecisionsThisMonth = decisions,
                TeamOvertimeMonthHours = teamRequests.Where(r => r.Kind == RequestKind.Overtime && r.StartDate.Year == today.Year && r.StartDate.Month == today.Month
                    && r.Status is not (RequestStatus.Cancelled or RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected)).Sum(r => r.TotalHours),
                TeamRequestsByKind = Enum.GetValues<RequestKind>().Select(k => new ChartPointDto(Labels.KindShort(k), teamRequests.Count(r => r.Kind == k), k.ToString().ToLowerInvariant())).ToList(),
                DepartmentStatus =
                [
                    new("En trámite", teamRequests.Count(r => r.Status is RequestStatus.PendingSupervisor or RequestStatus.PendingManager), "warning"),
                    new("Autorizadas", teamRequests.Count(r => r.Status is RequestStatus.ManagerApproved or RequestStatus.PendingAdministrativeRegistration or RequestStatus.AdministrativeObserved or RequestStatus.AdministrativeRegistered or RequestStatus.Completed), "success"),
                    new("Devueltas", teamRequests.Count(r => r.Status == RequestStatus.ReturnedForCorrection), "attention"),
                    new("Rechazadas", teamRequests.Count(r => r.Status is RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected), "danger"),
                ],
                OvertimeTrend = sixMonths.Select(m => new ChartPointDto(m.ToString("MMM", es).TrimEnd('.'),
                    teamRequests.Where(r => r.Kind == RequestKind.Overtime && r.StartDate.Year == m.Year && r.StartDate.Month == m.Month
                        && r.Status is not (RequestStatus.Cancelled or RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected)).Sum(r => r.TotalHours))).ToList(),
                UpcomingTeamAbsences = upcoming.Where(e => !e.IsHoliday && !e.IsMine).OrderBy(e => e.Start).Take(8).ToList()
            };
        }

        if (actor.Has(UserRole.AdministrativeRegistrar) || actor.Has(UserRole.ProductAdmin))
        {
            var counts = await db.Requests.AsNoTracking()
                .Where(r => r.Status == RequestStatus.PendingAdministrativeRegistration || r.Status == RequestStatus.AdministrativeObserved || r.Status == RequestStatus.AdministrativeRegistered)
                .GroupBy(r => r.Status).Select(g => new { g.Key, Count = g.Count() }).ToListAsync(ct);
            dto = dto with
            {
                AdminPendingRegistration = counts.FirstOrDefault(c => c.Key == RequestStatus.PendingAdministrativeRegistration)?.Count ?? 0,
                AdminObserved = counts.FirstOrDefault(c => c.Key == RequestStatus.AdministrativeObserved)?.Count ?? 0,
                AdminRegistered = counts.FirstOrDefault(c => c.Key == RequestStatus.AdministrativeRegistered)?.Count ?? 0,
            };
        }
        if (actor.Has(UserRole.ProductAdmin))
        {
            dto = dto with
            {
                ActiveEmployees = await db.Employees.CountAsync(e => e.IsActive, ct),
                EmailsPending = await db.EmailOutbox.CountAsync(m => m.Status == EmailStatus.Pending || m.Status == EmailStatus.Sending, ct),
                EmailsFailed = await db.EmailOutbox.CountAsync(m => m.Status == EmailStatus.Failed, ct),
            };
        }
        return dto;
    }

    /// <summary>
    /// Calendario. Los compañeros sin relación de mando solo ven "Ausencia en el equipo" (sin nombre ni motivo)
    /// para no revelar información personal innecesaria.
    /// </summary>
    public async Task<IReadOnlyList<CalendarEventDto>> GetCalendarAsync(Actor actor, DateOnly from, DateOnly to, CalendarScope scope, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        if (to < from || to.DayNumber - from.DayNumber > 120) throw new BusinessRuleException("Rango de calendario inválido (máximo 120 días).");
        var id = actor.EmployeeId;
        var isLeader = actor.Has(UserRole.DirectSupervisor) || actor.Has(UserRole.SeniorManager);
        var events = new List<CalendarEventDto>();

        var baseQuery = db.Requests.AsNoTracking()
            .Where(r => r.Status != RequestStatus.Draft && r.Status != RequestStatus.Cancelled && r.Status != RequestStatus.SupervisorRejected && r.Status != RequestStatus.ManagerRejected)
            .Where(r => r.Periods.Any(p => p.StartDate <= to && p.EndDate >= from));

        var own = await baseQuery.Where(r => r.EmployeeId == id).WithSummary().ToListAsync(ct);
        events.AddRange(own.Select(r => Event(r, true, true)));

        if (scope is CalendarScope.Team or CalendarScope.Department)
        {
            List<Request> others;
            bool named;
            if (scope == CalendarScope.Department && (actor.Has(UserRole.SeniorManager) || actor.Has(UserRole.ProductAdmin)))
            {
                others = await baseQuery.Where(r => r.EmployeeId != id).WithSummary().ToListAsync(ct);
                named = true;
            }
            else if (isLeader)
            {
                var team = db.TeamMemberIds(id);
                others = await baseQuery.Where(r => r.EmployeeId != id && team.Contains(r.EmployeeId)).WithSummary().ToListAsync(ct);
                named = true;
            }
            else
            {
                var supervisorId = await db.ReportingHierarchy.Where(h => h.EmployeeId == id && h.IsCurrent).Select(h => h.DirectSupervisorId).FirstOrDefaultAsync(ct);
                var peers = db.ReportingHierarchy.Where(h => h.IsCurrent && h.DirectSupervisorId == supervisorId && supervisorId != null).Select(h => h.EmployeeId);
                others = await baseQuery.Where(r => r.EmployeeId != id && r.Kind != RequestKind.Overtime && peers.Contains(r.EmployeeId)).WithSummary().ToListAsync(ct);
                named = false;
            }
            events.AddRange(others.Select(r => Event(r, false, named)));
        }

        var holidays = await db.Holidays.AsNoTracking().Where(h => h.IsActive && h.Date >= from && h.Date <= to).ToListAsync(ct);
        events.AddRange(holidays.Select(h => new CalendarEventDto(null, h.Name, h.Date, h.Date, null, null, false, true, "holiday")));
        return events.OrderBy(e => e.Start).ThenBy(e => e.Title).ToList();

        static CalendarEventDto Event(Request r, bool mine, bool named)
        {
            var p = r.PrimaryPeriod!;
            var tone = r.Kind switch { RequestKind.Overtime => "overtime", RequestKind.Vacation => "vacation", RequestKind.PaidLeave => "paidleave", _ => "unpaidleave" };
            return named
                ? new CalendarEventDto(r.Id, mine ? Labels.KindShort(r.Kind) : $"{r.Employee?.FullName} · {Labels.KindShort(r.Kind)}", p.StartDate, p.EndDate, r.Kind, r.Status, mine, false, tone)
                : new CalendarEventDto(null, "Ausencia en el equipo", p.StartDate, p.EndDate, null, null, false, false, "peer");
        }
    }

    public async Task<IReadOnlyList<SearchResultDto>> SearchAsync(Actor actor, string term, CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(term) || term.Trim().Length < 2) return [];
        var t = term.Trim().ToLower();
        var results = new List<SearchResultDto>();
        var requests = await db.Requests.AsNoTracking().VisibleTo(actor)
            .Where(r => r.Folio.ToLower().Contains(t) || r.Employee!.FullName.ToLower().Contains(t) || r.Employee.EmployeeNumber.ToLower().Contains(t))
            .OrderByDescending(r => r.CreatedAtUtc).Take(6).WithSummary().ToListAsync(ct);
        results.AddRange(requests.Select(r => new SearchResultDto("Solicitud", $"{r.Folio} · {Labels.KindShort(r.Kind)}",
            $"{r.Employee?.FullName} · {Labels.Status(r.Status)}", $"/solicitudes/{r.Id}")));
        if (actor.Has(UserRole.ProductAdmin))
        {
            var employees = await db.Employees.AsNoTracking()
                .Where(e => e.FullName.ToLower().Contains(t) || e.EmployeeNumber.ToLower().Contains(t) || e.NormalizedEmail.Contains(t))
                .OrderBy(e => e.FullName).Take(5).ToListAsync(ct);
            results.AddRange(employees.Select(e => new SearchResultDto("Empleado", e.FullName, $"{e.EmployeeNumber} · {e.Area}", $"/admin/empleados/{e.Id}")));
        }
        return results;
    }

    /// <summary>Verificación pública por QR: no expone datos personales, solo integridad y estado.</summary>
    public async Task<VerificationDto?> VerifyAsync(string folio, string? code, CancellationToken ct = default)
    {
        if (!FolioFormatter.IsValid(folio)) return null;
        var r = await db.Requests.AsNoTracking().Include(x => x.Periods).Include(x => x.Overtime).Include(x => x.Attachments).Include(x => x.Signatures).Include(x => x.Decisions)
            .FirstOrDefaultAsync(x => x.Folio == folio, ct);
        if (r is null || r.Status == RequestStatus.Draft) return null;
        if (string.IsNullOrWhiteSpace(code) || code.Length < 12 || !r.ContentHash.StartsWith(code, StringComparison.OrdinalIgnoreCase)) return null;
        var intact = RequestContentHasher.Compute(r) == r.ContentHash;
        var valid = r.Signatures.Count(s => s.IsValid && s.RequestVersion == r.Version && s.DocumentHash == r.ContentHash);
        return new VerificationDto(r.Folio, Labels.Status(r.Status), Labels.Kind(r.Kind), intact, valid,
            r.Decisions.OrderByDescending(d => d.OccurredAtUtc).FirstOrDefault()?.OccurredAtUtc,
            intact ? "El contenido coincide con la versión registrada en GPV Product TimeFlow." : "ADVERTENCIA: el contenido no coincide con la huella registrada.");
    }
}

public sealed class VacationService(ITimeFlowDbContext db, ActorGuard guard, RequestRules rules, SettingsService settings, LocalClock clock, AuditWriter audit)
{
    public async Task<VacationBalanceDto> GetBalanceAsync(Actor actor, int? employeeId = null, int? year = null, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var targetId = employeeId ?? actor.EmployeeId;
        if (targetId != actor.EmployeeId && !actor.Has(UserRole.ProductAdmin))
        {
            var isLeader = await db.TeamMemberIds(actor.EmployeeId).ContainsAsync(targetId, ct);
            if (!isLeader) throw new NotFoundException();
        }
        var y = year ?? clock.Today.Year;
        var employee = await db.Employees.AsNoTracking().FirstOrDefaultAsync(e => e.Id == targetId, ct) ?? throw new NotFoundException();
        var balance = await db.VacationBalances.AsNoTracking().Include(b => b.Transactions).FirstOrDefaultAsync(b => b.EmployeeId == targetId && b.PeriodYear == y, ct);
        var requests = await db.Requests.AsNoTracking().Where(r => r.EmployeeId == targetId && r.Kind == RequestKind.Vacation && r.Periods.Any(p => p.StartDate.Year == y))
            .OrderByDescending(r => r.CreatedAtUtc).WithSummary().ToListAsync(ct);
        var today = clock.Today;
        var txs = balance?.Transactions ?? [];
        var requestEnd = requests.ToDictionary(r => r.Id, r => r.PrimaryPeriod!.EndDate);
        var consumption = txs.Where(t => t.Type == VacationTransactionType.Consumption).ToList();
        var used = -consumption.Where(t => t.RequestId is Guid id && requestEnd.TryGetValue(id, out var end) && end < today).Sum(t => t.Days);
        var upcoming = -consumption.Sum(t => t.Days) - used;
        var pending = await rules.PendingVacationDaysAsync(targetId, y, null, ct);
        var adjustments = txs.Where(t => t.Type is VacationTransactionType.Adjustment or VacationTransactionType.Reversal or VacationTransactionType.Entitlement).Sum(t => t.Days);
        var folios = requests.ToDictionary(r => r.Id, r => r.Folio);
        return new VacationBalanceDto
        {
            EmployeeId = targetId,
            EmployeeName = employee.FullName,
            PeriodYear = y,
            Entitled = balance?.EntitledDays ?? 0,
            Adjustments = adjustments,
            Used = used,
            ApprovedUpcoming = upcoming,
            Pending = pending,
            Available = (balance?.EntitledDays ?? 0) + txs.Sum(t => t.Days) - pending,
            PendingRequests = requests.Count(r => r.IsOpen || r.Status == RequestStatus.ReturnedForCorrection),
            RejectedRequests = requests.Count(r => r.IsRejected),
            Transactions = txs.OrderByDescending(t => t.CreatedAtUtc).Select(t => new VacationTransactionDto(t.CreatedAtUtc, Labels.VacationTransaction(t.Type), t.Days,
                t.RequestId is Guid rid ? folios.GetValueOrDefault(rid) : null, t.Description, t.CreatedByName)).ToList(),
            Requests = requests.Select(r => DtoMapper.ToSummary(r)).ToList()
        };
    }

    public async Task<VacationPreviewDto> PreviewAsync(Actor actor, VacationPreviewRequest input, CancellationToken ct = default)
    {
        var employee = await guard.RequireActiveAsync(actor, ct);
        var calendar = await settings.GetCalendarAsync(ct);
        var errors = new List<string>();
        var warnings = new List<string>();
        var end = input.EndDate < input.StartDate ? input.StartDate : input.EndDate;
        var businessDays = calendar.CountWorkingDays(input.StartDate, end);
        var available = await rules.AvailableVacationDaysAsync(employee.Id, input.StartDate.Year, input.ExcludeRequestId, ct);
        try
        {
            await rules.ValidateAsync(employee, new RequestInput { Kind = RequestKind.Vacation, StartDate = input.StartDate, EndDate = input.EndDate, Reason = "Vista previa" }, input.ExcludeRequestId, ct);
        }
        catch (BusinessRuleException ex) { errors.AddRange(ex.Errors); }

        // Compañeros ausentes en el rango (mismo jefe directo). Nombres solo para líderes.
        var supervisorId = await db.ReportingHierarchy.Where(h => h.EmployeeId == employee.Id && h.IsCurrent).Select(h => h.DirectSupervisorId).FirstOrDefaultAsync(ct);
        var isLeader = actor.Has(UserRole.DirectSupervisor) || actor.Has(UserRole.SeniorManager);
        var peers = db.ReportingHierarchy.Where(h => h.IsCurrent && supervisorId != null && h.DirectSupervisorId == supervisorId && h.EmployeeId != employee.Id).Select(h => h.EmployeeId);
        var absent = await db.Requests.AsNoTracking()
            .Where(r => peers.Contains(r.EmployeeId) && r.Kind != RequestKind.Overtime
                && r.Status != RequestStatus.Draft && r.Status != RequestStatus.Cancelled && r.Status != RequestStatus.SupervisorRejected && r.Status != RequestStatus.ManagerRejected
                && r.Periods.Any(p => p.StartDate <= end && p.EndDate >= input.StartDate))
            .Select(r => r.Employee!.FullName).Distinct().ToListAsync(ct);
        if (absent.Count > 0) warnings.Add($"{absent.Count} {(absent.Count == 1 ? "compañero(a) de tu equipo estará ausente" : "compañeros de tu equipo estarán ausentes")} en esas fechas.");

        return new VacationPreviewDto(businessDays, end.DayNumber - input.StartDate.DayNumber + 1, calendar.HolidaysBetween(input.StartDate, end),
            available, available - businessDays, absent.Count, isLeader ? absent : [], errors, warnings);
    }

    /// <summary>Ajuste de saldo por Administrador de Producto (en coordinación con RH). Siempre auditado.</summary>
    public async Task AdjustAsync(Actor actor, int employeeId, int year, decimal days, string reason, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        if (days == 0 || Math.Abs(days) > 60) throw new BusinessRuleException("El ajuste debe ser distinto de cero y menor a 60 días.");
        if (string.IsNullOrWhiteSpace(reason) || reason.Trim().Length < 10) throw new BusinessRuleException("Indique el motivo del ajuste (mínimo 10 caracteres).");
        var balance = await db.VacationBalances.FirstOrDefaultAsync(b => b.EmployeeId == employeeId && b.PeriodYear == year, ct);
        if (balance is null)
        {
            if (!await db.Employees.AnyAsync(e => e.Id == employeeId, ct)) throw new NotFoundException();
            balance = new VacationBalance { EmployeeId = employeeId, PeriodYear = year, EntitledDays = 0 };
            db.VacationBalances.Add(balance);
        }
        var tx = new VacationTransaction
        {
            Id = Guid.NewGuid(), Type = VacationTransactionType.Adjustment, Days = days, Description = reason.Trim(),
            CreatedByEmployeeId = actor.EmployeeId, CreatedByName = actor.Name, CreatedAtUtc = clock.UtcNow
        };
        balance.Transactions.Add(tx);
        db.VacationTransactions.Add(tx);
        audit.Write(actor, "vacation.adjusted", nameof(VacationBalance), $"{employeeId}:{year}", new { days, reason });
        await db.SaveChangesAsync(ct);
    }
}

public sealed class OvertimeService(ITimeFlowDbContext db, ActorGuard guard, RequestRules rules, SettingsService settings)
{
    public async Task<OvertimePreviewDto> PreviewAsync(Actor actor, OvertimePreviewRequest input, CancellationToken ct = default)
    {
        var employee = await guard.RequireActiveAsync(actor, ct);
        var calc = OvertimeCalculator.Calculate(input.Date, input.Start, input.End);
        var errors = new List<string>();
        var warnings = new List<string>();
        try
        {
            var computed = await rules.ValidateAsync(employee, new RequestInput
            {
                Kind = RequestKind.Overtime, StartDate = input.Date, StartTime = input.Start, EndTime = input.End,
                Reason = "Vista previa", Project = "Vista previa", Activity = "Vista previa"
            }, input.ExcludeRequestId, ct);
            warnings.AddRange(computed.Warnings);
        }
        catch (BusinessRuleException ex) { errors.AddRange(ex.Errors); }
        if (calc.CrossesMidnight && !warnings.Any(w => w.Contains("medianoche"))) warnings.Add("El horario cruza la medianoche: termina al día siguiente.");
        return new OvertimePreviewDto(calc.Hours, calc.CrossesMidnight, calc.StartLocal, calc.EndLocal, errors, warnings);
    }

    public async Task<OvertimeMonthlySummaryDto> MonthlySummaryAsync(Actor actor, int year, int month, int? employeeId = null, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var target = employeeId ?? actor.EmployeeId;
        if (target != actor.EmployeeId && !actor.Has(UserRole.ProductAdmin) && !await db.TeamMemberIds(actor.EmployeeId).ContainsAsync(target, ct))
            throw new NotFoundException();
        var policy = await settings.GetPolicyAsync(ct);
        var items = await db.Requests.AsNoTracking()
            .Where(r => r.EmployeeId == target && r.Kind == RequestKind.Overtime && r.Overtime!.PeriodYear == year && r.Overtime.PeriodMonth == month)
            .OrderByDescending(r => r.CreatedAtUtc).WithSummary().ToListAsync(ct);
        var dtos = items.Select(r => DtoMapper.ToSummary(r, policy.UrgentAfterHours)).ToList();
        var active = items.Where(r => r.Status is not (RequestStatus.Draft or RequestStatus.Cancelled)).ToList();
        return new OvertimeMonthlySummaryDto(year, month,
            active.Sum(r => r.TotalHours),
            active.Where(r => r.IsFinalApproved).Sum(r => r.TotalHours),
            active.Where(r => r.IsRejected).Sum(r => r.TotalHours),
            active.Where(r => r.IsOpen || r.Status == RequestStatus.ReturnedForCorrection).Sum(r => r.TotalHours),
            dtos);
    }
}

public sealed class NotificationService(ITimeFlowDbContext db, LocalClock clock)
{
    public async Task<PagedResult<NotificationDto>> ListAsync(Actor actor, bool unreadOnly, int page = 1, int pageSize = 20, CancellationToken ct = default)
    {
        var q = db.Notifications.AsNoTracking().Where(n => n.RecipientEmployeeId == actor.EmployeeId);
        if (unreadOnly) q = q.Where(n => n.ReadAtUtc == null);
        var total = await q.CountAsync(ct);
        pageSize = Math.Clamp(pageSize, 1, 100);
        var items = await q.OrderByDescending(n => n.CreatedAtUtc).Skip((Math.Max(1, page) - 1) * pageSize).Take(pageSize).ToListAsync(ct);
        return new PagedResult<NotificationDto>(items.Select(DtoMapper.ToDto).ToList(), page, pageSize, total);
    }

    public Task<int> UnreadCountAsync(Actor actor, CancellationToken ct = default) =>
        db.Notifications.CountAsync(n => n.RecipientEmployeeId == actor.EmployeeId && n.ReadAtUtc == null, ct);

    public async Task MarkReadAsync(Actor actor, Guid id, CancellationToken ct = default)
    {
        var n = await db.Notifications.FirstOrDefaultAsync(x => x.Id == id && x.RecipientEmployeeId == actor.EmployeeId, ct) ?? throw new NotFoundException();
        n.ReadAtUtc ??= clock.UtcNow;
        await db.SaveChangesAsync(ct);
    }

    public async Task<int> MarkAllReadAsync(Actor actor, CancellationToken ct = default)
    {
        var items = await db.Notifications.Where(x => x.RecipientEmployeeId == actor.EmployeeId && x.ReadAtUtc == null).ToListAsync(ct);
        foreach (var n in items) n.ReadAtUtc = clock.UtcNow;
        await db.SaveChangesAsync(ct);
        return items.Count;
    }
}
