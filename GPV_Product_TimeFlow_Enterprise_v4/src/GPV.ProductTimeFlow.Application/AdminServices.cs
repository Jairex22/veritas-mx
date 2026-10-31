using System.Globalization;
using System.Net.Mail;
using System.Text.Json;
using System.Text.RegularExpressions;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace GPV.ProductTimeFlow.Application;

/// <summary>Gestión de empleados, jerarquía y roles. Exclusivo del Administrador de Producto.</summary>
public sealed partial class EmployeeAdminService(
    ITimeFlowDbContext db, ActorGuard guard, AuditWriter audit, LocalClock clock, IPasswordService passwords,
    IExcelImporter importer, IOptions<DemoOptions> demo, EnvironmentInfo env)
{
    public async Task<PagedResult<EmployeeDto>> ListAsync(Actor actor, string? search, bool includeInactive, int page, int pageSize, CancellationToken ct = default)
    {
        await RequireAdminOrLeaderAsync(actor, ct);
        var q = db.Employees.AsNoTracking().AsQueryable();
        if (!actor.Has(UserRole.ProductAdmin))
        {
            var team = db.TeamMemberIds(actor.EmployeeId);
            q = q.Where(e => team.Contains(e.Id));
        }
        if (!includeInactive) q = q.Where(e => e.IsActive);
        if (!string.IsNullOrWhiteSpace(search))
        {
            var t = search.Trim().ToLower();
            q = q.Where(e => e.FullName.ToLower().Contains(t) || e.EmployeeNumber.ToLower().Contains(t) || e.NormalizedEmail.Contains(t) || (e.Area != null && e.Area.ToLower().Contains(t)));
        }
        var total = await q.CountAsync(ct);
        pageSize = Math.Clamp(pageSize, 1, 200);
        var ids = await q.OrderBy(e => e.FullName).Skip((Math.Max(1, page) - 1) * pageSize).Take(pageSize).Select(e => e.Id).ToListAsync(ct);
        var items = await ProjectAsync(ids, ct);
        return new PagedResult<EmployeeDto>(items, page, pageSize, total);
    }

    public async Task<EmployeeDto> GetAsync(Actor actor, int id, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        return (await ProjectAsync([id], ct)).FirstOrDefault() ?? throw new NotFoundException();
    }

    private async Task<List<EmployeeDto>> ProjectAsync(IReadOnlyCollection<int> ids, CancellationToken ct)
    {
        var year = clock.Today.Year;
        var employees = await db.Employees.AsNoTracking().Include(e => e.Department).Include(e => e.Position).Include(e => e.User)
            .Where(e => ids.Contains(e.Id)).ToListAsync(ct);
        var hierarchy = await db.ReportingHierarchy.AsNoTracking().Include(h => h.DirectSupervisor).Include(h => h.SeniorManager)
            .Where(h => h.IsCurrent && ids.Contains(h.EmployeeId)).ToListAsync(ct);
        var balances = await db.VacationBalances.AsNoTracking().Include(b => b.Transactions).Where(b => b.PeriodYear == year && ids.Contains(b.EmployeeId)).ToListAsync(ct);
        var now = clock.UtcNow;
        return ids.Select(id => employees.FirstOrDefault(e => e.Id == id)).Where(e => e is not null).Select(e =>
        {
            var h = hierarchy.FirstOrDefault(x => x.EmployeeId == e!.Id);
            var b = balances.FirstOrDefault(x => x.EmployeeId == e!.Id);
            return new EmployeeDto
            {
                Id = e!.Id, EmployeeNumber = e.EmployeeNumber, FullName = e.FullName, Email = e.Email, DepartmentId = e.DepartmentId,
                Department = e.Department?.Name ?? "", Area = e.Area, PositionId = e.PositionId, Position = e.Position?.Name,
                SupervisorId = h?.DirectSupervisorId, SupervisorName = h?.DirectSupervisor?.FullName, ManagerId = h?.SeniorManagerId, ManagerName = h?.SeniorManager?.FullName,
                IsActive = e.IsActive, HireDate = e.HireDate, Roles = e.User?.Roles ?? UserRole.None,
                VacationAvailable = b is null ? 0 : b.EntitledDays + b.Transactions.Sum(t => t.Days),
                HasLocalLogin = e.User?.PasswordHash is not null, IsLockedOut = e.User?.LockoutEndUtc > now
            };
        }).ToList();
    }

    public async Task<int> CreateAsync(Actor actor, EmployeeInput input, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        await ValidateAsync(input, null, ct);
        var now = clock.UtcNow;
        var employee = new Employee
        {
            EmployeeNumber = input.EmployeeNumber.Trim().ToUpperInvariant(), FullName = input.FullName.Trim(), Email = input.Email.Trim(),
            NormalizedEmail = input.Email.Trim().ToLowerInvariant(), DepartmentId = input.DepartmentId, Area = Text.Clean(input.Area),
            PositionId = input.PositionId, HireDate = input.HireDate, IsActive = input.IsActive, IsSynthetic = env.Mode != EnvironmentMode.Production
        };
        employee.User = new UserAccount
        {
            Roles = input.Roles | UserRole.Employee, IsActive = input.IsActive,
            PasswordHash = env.Mode == EnvironmentMode.Production ? null : passwords.Hash(demo.Value.Password)
        };
        db.Employees.Add(employee);
        await db.SaveChangesAsync(ct);
        db.ReportingHierarchy.Add(new ReportingHierarchy
        {
            EmployeeId = employee.Id, DirectSupervisorId = input.SupervisorId, SeniorManagerId = input.ManagerId, EffectiveFrom = clock.Today, IsCurrent = true
        });
        var days = input.InitialVacationDays ?? (input.HireDate is DateOnly hd
            ? VacationEntitlementPolicy.DaysForYearsOfService(VacationEntitlementPolicy.CompletedYears(hd, clock.Today)) : 12);
        db.VacationBalances.Add(new VacationBalance { EmployeeId = employee.Id, PeriodYear = clock.Today.Year, EntitledDays = days });
        audit.Write(actor, "employee.created", nameof(Employee), employee.Id.ToString(), new { employee.EmployeeNumber, Roles = employee.User.Roles.ToString() });
        await db.SaveChangesAsync(ct);
        return employee.Id;
    }

    public async Task UpdateAsync(Actor actor, int id, EmployeeInput input, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var employee = await db.Employees.Include(e => e.User).FirstOrDefaultAsync(e => e.Id == id, ct) ?? throw new NotFoundException();
        await ValidateAsync(input, id, ct);
        if (id == actor.EmployeeId && (!input.IsActive || !input.Roles.HasFlag(UserRole.ProductAdmin)))
            throw new BusinessRuleException("No puede retirarse a sí mismo el rol de administrador ni desactivar su propia cuenta.");
        var before = new { employee.EmployeeNumber, employee.Email, Roles = employee.User?.Roles.ToString(), employee.IsActive };
        employee.EmployeeNumber = input.EmployeeNumber.Trim().ToUpperInvariant();
        employee.FullName = input.FullName.Trim();
        employee.Email = input.Email.Trim();
        employee.NormalizedEmail = input.Email.Trim().ToLowerInvariant();
        employee.DepartmentId = input.DepartmentId;
        employee.Area = Text.Clean(input.Area);
        employee.PositionId = input.PositionId;
        employee.HireDate = input.HireDate;
        employee.IsActive = input.IsActive;
        employee.User ??= new UserAccount();
        var roles = input.Roles | UserRole.Employee;
        if (employee.User.Roles != roles || employee.User.IsActive != input.IsActive) employee.User.SecurityStamp = Guid.NewGuid();
        employee.User.Roles = roles;
        employee.User.IsActive = input.IsActive;

        var current = await db.ReportingHierarchy.FirstOrDefaultAsync(h => h.EmployeeId == id && h.IsCurrent, ct);
        if (current is null || current.DirectSupervisorId != input.SupervisorId || current.SeniorManagerId != input.ManagerId)
        {
            if (current is not null) { current.IsCurrent = false; current.EffectiveTo = clock.Today; }
            db.ReportingHierarchy.Add(new ReportingHierarchy { EmployeeId = id, DirectSupervisorId = input.SupervisorId, SeniorManagerId = input.ManagerId, EffectiveFrom = clock.Today, IsCurrent = true });
        }
        audit.Write(actor, "employee.updated", nameof(Employee), id.ToString(), new { before, after = new { employee.EmployeeNumber, employee.Email, Roles = roles.ToString(), employee.IsActive, input.SupervisorId, input.ManagerId } });
        await db.SaveChangesAsync(ct);
    }

    public async Task UnlockAsync(Actor actor, int id, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var user = await db.Users.FirstOrDefaultAsync(u => u.EmployeeId == id, ct) ?? throw new NotFoundException();
        user.LockoutEndUtc = null;
        user.FailedLoginCount = 0;
        audit.Write(actor, "user.unlocked", nameof(UserAccount), id.ToString());
        await db.SaveChangesAsync(ct);
    }

    private async Task ValidateAsync(EmployeeInput input, int? id, CancellationToken ct)
    {
        var errors = RequestRules.Annotations(input);
        var number = input.EmployeeNumber.Trim().ToUpperInvariant();
        var email = input.Email.Trim().ToLowerInvariant();
        if (await db.Employees.AnyAsync(e => e.EmployeeNumber == number && e.Id != id, ct)) errors.Add($"Ya existe un empleado con el número {number}.");
        if (await db.Employees.AnyAsync(e => e.NormalizedEmail == email && e.Id != id, ct)) errors.Add($"Ya existe un empleado con el correo {email}.");
        if (!await db.Departments.AnyAsync(d => d.Id == input.DepartmentId && d.IsActive, ct)) errors.Add("El departamento no existe.");
        if (input.PositionId is int pid && !await db.Positions.AnyAsync(p => p.Id == pid, ct)) errors.Add("El puesto no existe.");
        if (input.SupervisorId is int s)
        {
            if (s == id) errors.Add("Un empleado no puede ser su propia jefa directa.");
            else if (!await db.Employees.AnyAsync(e => e.Id == s && e.IsActive, ct)) errors.Add("La jefa directa seleccionada no existe o está inactiva.");
        }
        if (input.ManagerId is int m)
        {
            if (m == id) errors.Add("Un empleado no puede ser su propio jefe superior.");
            else if (!await db.Employees.AnyAsync(e => e.Id == m && e.IsActive, ct)) errors.Add("El jefe superior seleccionado no existe o está inactivo.");
        }
        if (input.SupervisorId is not null && input.SupervisorId == input.ManagerId) errors.Add("La jefa directa y el jefe superior deben ser personas distintas.");
        if (errors.Count > 0) throw new BusinessRuleException(errors);
    }

    public async Task<IReadOnlyList<LookupDto>> DepartmentsAsync(CancellationToken ct = default) =>
        await db.Departments.AsNoTracking().Where(d => d.IsActive).OrderBy(d => d.Name).Select(d => new LookupDto(d.Id, d.Name)).ToListAsync(ct);

    public async Task<IReadOnlyList<LookupDto>> PositionsAsync(CancellationToken ct = default) =>
        await db.Positions.AsNoTracking().Where(d => d.IsActive).OrderBy(d => d.Name).Select(d => new LookupDto(d.Id, d.Name)).ToListAsync(ct);

    public async Task<IReadOnlyList<LookupDto>> LeadersAsync(UserRole role, CancellationToken ct = default) =>
        await db.Employees.AsNoTracking().Where(e => e.IsActive && e.User != null && (e.User.Roles & role) == role)
            .OrderBy(e => e.FullName).Select(e => new LookupDto(e.Id, e.FullName)).ToListAsync(ct);

    public async Task<IReadOnlyList<OrgNodeDto>> OrgChartAsync(Actor actor, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var employees = await db.Employees.AsNoTracking().Include(e => e.User).Include(e => e.Position).Where(e => e.IsActive).ToListAsync(ct);
        var rows = await db.ReportingHierarchy.AsNoTracking().Where(h => h.IsCurrent).ToListAsync(ct);
        var supervisorOf = rows.ToDictionary(h => h.EmployeeId, h => h.DirectSupervisorId);
        var managerOf = rows.ToDictionary(h => h.EmployeeId, h => h.SeniorManagerId);
        var byId = employees.ToDictionary(e => e.Id);

        OrgNodeDto Node(Employee e, HashSet<int> path)
        {
            path.Add(e.Id);
            var reports = employees.Where(x => !path.Contains(x.Id) && ParentOf(x.Id) == e.Id).OrderBy(x => x.FullName).Select(x => Node(x, [.. path])).ToList();
            return new OrgNodeDto(e.Id, e.FullName, e.Position?.Name, e.Area, e.User?.Roles ?? UserRole.None, reports);
        }
        int? ParentOf(int id)
        {
            var sup = supervisorOf.GetValueOrDefault(id);
            // Las jefas directas se cuelgan de su jefe superior.
            return sup is int s && byId.ContainsKey(s) && s != id ? s : managerOf.GetValueOrDefault(id) is int m && byId.ContainsKey(m) && m != id ? m : null;
        }
        return employees.Where(e => ParentOf(e.Id) is null).OrderByDescending(e => (int)(e.User?.Roles ?? 0)).ThenBy(e => e.FullName).Select(e => Node(e, [])).ToList();
    }

    /// <summary>Importación controlada desde Excel: valida todo, informa fila por fila y solo aplica si no es simulación.</summary>
    public async Task<ImportResultDto> ImportAsync(Actor actor, Stream workbook, bool dryRun, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        IReadOnlyList<EmployeeImportRow> rows;
        try { rows = importer.ReadEmployees(workbook); }
        catch (Exception ex) when (ex is not BusinessRuleException) { throw new BusinessRuleException("El archivo no es un libro de Excel válido o no usa la plantilla oficial."); }
        if (rows.Count > 1000) throw new BusinessRuleException("Máximo 1000 filas por importación.");

        var departments = await db.Departments.ToListAsync(ct);
        var positions = await db.Positions.ToListAsync(ct);
        var existing = await db.Employees.Include(e => e.User).ToListAsync(ct);
        var results = new List<ImportRowResultDto>();
        var seenNumbers = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var seenEmails = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var pending = new List<(EmployeeImportRow Row, Employee? Existing)>();

        foreach (var row in rows)
        {
            var errs = new List<string>();
            var number = row.EmployeeNumber?.Trim().ToUpperInvariant();
            var email = row.Email?.Trim().ToLowerInvariant();
            if (string.IsNullOrWhiteSpace(number) || !EmployeeNumberRegex().IsMatch(number)) errs.Add("número de empleado inválido");
            if (string.IsNullOrWhiteSpace(row.FullName) || row.FullName.Trim().Length < 3) errs.Add("nombre inválido");
            if (string.IsNullOrWhiteSpace(email) || !MailAddress.TryCreate(email, out _)) errs.Add("correo inválido");
            if (number is not null && !seenNumbers.Add(number)) errs.Add("número duplicado en el archivo");
            if (email is not null && !seenEmails.Add(email)) errs.Add("correo duplicado en el archivo");
            var match = existing.FirstOrDefault(e => e.EmployeeNumber == number);
            if (email is not null && existing.Any(e => e.NormalizedEmail == email && e.EmployeeNumber != number)) errs.Add("el correo ya pertenece a otro empleado");
            if (!string.IsNullOrWhiteSpace(row.Department) && !departments.Any(d => d.Name.Equals(row.Department.Trim(), StringComparison.OrdinalIgnoreCase)))
                errs.Add($"departamento «{row.Department}» no existe");
            if (errs.Count > 0) { results.Add(new(row.RowNumber, number, false, string.Join("; ", errs))); continue; }
            pending.Add((row, match));
            results.Add(new(row.RowNumber, number, true, match is null ? "Se creará" : "Se actualizará"));
        }

        int created = 0, updated = 0;
        if (!dryRun && pending.Count > 0)
        {
            await using var tx = await db.Database.BeginTransactionAsync(ct);
            var defaultDept = departments.First(d => d.IsActive);
            foreach (var (row, match) in pending)
            {
                var dept = departments.FirstOrDefault(d => d.Name.Equals(row.Department?.Trim(), StringComparison.OrdinalIgnoreCase)) ?? defaultDept;
                var pos = string.IsNullOrWhiteSpace(row.Position) ? null : positions.FirstOrDefault(p => p.Name.Equals(row.Position.Trim(), StringComparison.OrdinalIgnoreCase));
                if (pos is null && !string.IsNullOrWhiteSpace(row.Position)) { pos = new Position { Name = row.Position.Trim() }; db.Positions.Add(pos); positions.Add(pos); }
                var e = match ?? new Employee { IsSynthetic = env.Mode != EnvironmentMode.Production };
                e.EmployeeNumber = row.EmployeeNumber!.Trim().ToUpperInvariant();
                e.FullName = row.FullName!.Trim();
                e.Email = row.Email!.Trim();
                e.NormalizedEmail = e.Email.ToLowerInvariant();
                e.Department = dept; e.DepartmentId = dept.Id;
                e.Area = Text.Clean(row.Area);
                e.Position = pos;
                e.HireDate = row.HireDate ?? e.HireDate;
                e.IsActive = true;
                e.User ??= new UserAccount { PasswordHash = env.Mode == EnvironmentMode.Production ? null : passwords.Hash(demo.Value.Password) };
                e.User.Roles = ParseRoles(row.Roles) | UserRole.Employee;
                e.User.IsActive = true;
                if (match is null) { db.Employees.Add(e); existing.Add(e); created++; } else updated++;
            }
            await db.SaveChangesAsync(ct);

            // Segunda pasada: jerarquía por correo (los líderes pueden venir en el mismo archivo).
            foreach (var (row, _) in pending)
            {
                var e = existing.First(x => x.EmployeeNumber == row.EmployeeNumber!.Trim().ToUpperInvariant());
                var sup = existing.FirstOrDefault(x => x.NormalizedEmail == row.SupervisorEmail?.Trim().ToLowerInvariant());
                var mgr = existing.FirstOrDefault(x => x.NormalizedEmail == row.ManagerEmail?.Trim().ToLowerInvariant());
                var current = await db.ReportingHierarchy.FirstOrDefaultAsync(h => h.EmployeeId == e.Id && h.IsCurrent, ct);
                if (current is null || current.DirectSupervisorId != sup?.Id || current.SeniorManagerId != mgr?.Id)
                {
                    if (current is not null) { current.IsCurrent = false; current.EffectiveTo = clock.Today; }
                    db.ReportingHierarchy.Add(new ReportingHierarchy { EmployeeId = e.Id, DirectSupervisorId = sup?.Id == e.Id ? null : sup?.Id, SeniorManagerId = mgr?.Id == e.Id ? null : mgr?.Id, EffectiveFrom = clock.Today, IsCurrent = true });
                }
                if (row.VacationDays is decimal vd && !await db.VacationBalances.AnyAsync(b => b.EmployeeId == e.Id && b.PeriodYear == clock.Today.Year, ct))
                    db.VacationBalances.Add(new VacationBalance { EmployeeId = e.Id, PeriodYear = clock.Today.Year, EntitledDays = vd });
            }
            audit.Write(actor, "employee.imported", nameof(Employee), "bulk", new { created, updated, failed = results.Count(r => !r.Success) });
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }
        return new ImportResultDto(created, updated, results.Count(r => !r.Success), results, dryRun);
    }

    internal static UserRole ParseRoles(string? csv)
    {
        var roles = UserRole.Employee;
        foreach (var token in (csv ?? "").Split([',', ';', '|'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var t = token.ToLowerInvariant();
            if (t.Contains("jefa") || t.Contains("directo") || t == "supervisor") roles |= UserRole.DirectSupervisor;
            else if (t.Contains("superior") || t == "manager" || t.Contains("gerente")) roles |= UserRole.SeniorManager;
            else if (t.Contains("admin")) roles |= UserRole.ProductAdmin;
            else if (t.Contains("registro") || t.Contains("rh")) roles |= UserRole.AdministrativeRegistrar;
        }
        return roles;
    }

    private async Task RequireAdminOrLeaderAsync(Actor actor, CancellationToken ct)
    {
        var e = await guard.RequireActiveAsync(actor, ct);
        var r = e.User!.Roles;
        if (!r.HasFlag(UserRole.ProductAdmin) && !r.HasFlag(UserRole.DirectSupervisor) && !r.HasFlag(UserRole.SeniorManager)) throw new ForbiddenException();
    }

    [GeneratedRegex("^[A-Z0-9-]{1,20}$")]
    private static partial Regex EmployeeNumberRegex();
}

public sealed class DemoOptions
{
    public const string Section = "Demo";
    /// <summary>Contraseña sintética común de las cuentas DEMO. Nunca usar en producción.</summary>
    public string Password { get; set; } = "Demo#TimeFlow2026";
    public int SyntheticEmployees { get; set; } = 200;
    public bool SeedSampleRequests { get; set; } = true;
}

public sealed partial class SettingsAdminService(ITimeFlowDbContext db, ActorGuard guard, SettingsService settings, AuditWriter audit)
{
    public Task<PolicySettingsDto> GetPolicyAsync(CancellationToken ct = default) => settings.GetPolicyAsync(ct);

    public async Task UpdatePolicyAsync(Actor actor, PolicySettingsDto dto, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var errors = RequestRules.Annotations(dto);
        if (!HexColor().IsMatch(dto.BrandPrimaryColor)) errors.Add("El color debe tener formato #RRGGBB.");
        if (WorkCalendar.ParseWorkingDays(dto.WorkingDays).Count == 0) errors.Add("Indique al menos un día hábil (1 = lunes … 7 = domingo).");
        if (!MailAddress.TryCreate(dto.AdministrativeMailbox, out _)) errors.Add("El buzón administrativo no es un correo válido.");
        if (dto.OvertimeMinHours > dto.OvertimeMaxHoursPerRequest) errors.Add("El mínimo de horas no puede ser mayor que el máximo por solicitud.");
        if (errors.Count > 0) throw new BusinessRuleException(errors);
        var before = JsonSerializer.Serialize(await settings.GetPolicyAsync(ct));
        await settings.SavePolicyAsync(dto, actor.Name, ct);
        audit.Write(actor, "settings.policy_updated", nameof(SystemSetting), "Policy", new { before, after = JsonSerializer.Serialize(dto) });
        await db.SaveChangesAsync(ct);
    }

    public async Task<IReadOnlyList<HolidayDto>> HolidaysAsync(int? year = null, CancellationToken ct = default)
    {
        var q = db.Holidays.AsNoTracking();
        if (year is int y) q = q.Where(h => h.Date >= new DateOnly(y, 1, 1) && h.Date <= new DateOnly(y, 12, 31));
        return await q.OrderBy(h => h.Date).Select(h => new HolidayDto(h.Id, h.Date, h.Name, h.IsActive)).ToListAsync(ct);
    }

    public async Task SaveHolidayAsync(Actor actor, HolidayDto dto, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        if (string.IsNullOrWhiteSpace(dto.Name) || dto.Name.Length > 120) throw new BusinessRuleException("Indique el nombre del día festivo.");
        if (await db.Holidays.AnyAsync(h => h.Date == dto.Date && h.Id != dto.Id, ct)) throw new BusinessRuleException("Ya existe un día festivo en esa fecha.");
        var h = dto.Id == 0 ? null : await db.Holidays.FirstOrDefaultAsync(x => x.Id == dto.Id, ct);
        if (h is null) { h = new Holiday(); db.Holidays.Add(h); }
        h.Date = dto.Date; h.Name = dto.Name.Trim(); h.IsActive = dto.IsActive;
        audit.Write(actor, "settings.holiday_saved", nameof(Holiday), dto.Date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), new { dto.Name, dto.IsActive });
        await db.SaveChangesAsync(ct);
    }

    public async Task<IReadOnlyList<LeaveCategoryDto>> CategoriesAsync(RequestKind? kind = null, bool activeOnly = false, CancellationToken ct = default)
    {
        var q = db.LeaveCategories.AsNoTracking();
        if (kind is RequestKind k) q = q.Where(c => c.AppliesTo == k);
        if (activeOnly) q = q.Where(c => c.IsActive);
        return await q.OrderBy(c => c.AppliesTo).ThenBy(c => c.Name).Select(c => new LeaveCategoryDto(c.Id, c.Name, c.AppliesTo, c.RequiresAttachment, c.IsActive)).ToListAsync(ct);
    }

    public async Task SaveCategoryAsync(Actor actor, LeaveCategoryDto dto, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        if (string.IsNullOrWhiteSpace(dto.Name) || dto.Name.Length > 100) throw new BusinessRuleException("Indique el nombre de la clasificación.");
        if (dto.AppliesTo is not (RequestKind.PaidLeave or RequestKind.UnpaidLeave)) throw new BusinessRuleException("La clasificación aplica solo a permisos.");
        var c = dto.Id == 0 ? null : await db.LeaveCategories.FirstOrDefaultAsync(x => x.Id == dto.Id, ct);
        if (c is null) { c = new LeaveCategory(); db.LeaveCategories.Add(c); }
        c.Name = dto.Name.Trim(); c.AppliesTo = dto.AppliesTo; c.RequiresAttachment = dto.RequiresAttachment; c.IsActive = dto.IsActive;
        audit.Write(actor, "settings.category_saved", nameof(LeaveCategory), dto.Id.ToString(CultureInfo.InvariantCulture), new { dto.Name, dto.AppliesTo, dto.IsActive });
        await db.SaveChangesAsync(ct);
    }

    [GeneratedRegex("^#[0-9A-Fa-f]{6}$")]
    private static partial Regex HexColor();
}

public sealed class AuditService(ITimeFlowDbContext db, ActorGuard guard, LocalClock clock)
{
    public async Task<PagedResult<AuditEntryDto>> ListAsync(Actor actor, string? search, int page, int pageSize, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var q = db.AuditLogs.AsNoTracking();
        if (!string.IsNullOrWhiteSpace(search))
        {
            var t = search.Trim().ToLower();
            q = q.Where(a => a.Action.ToLower().Contains(t) || a.ActorName.ToLower().Contains(t) || a.EntityId.ToLower().Contains(t) || (a.Details != null && a.Details.ToLower().Contains(t)));
        }
        var total = await q.CountAsync(ct);
        pageSize = Math.Clamp(pageSize, 1, 200);
        var items = await q.OrderByDescending(a => a.Sequence).Skip((Math.Max(1, page) - 1) * pageSize).Take(pageSize)
            .Select(a => new AuditEntryDto(a.Id, a.OccurredAtUtc, a.ActorName, a.Action, a.EntityType, a.EntityId, a.Details, a.IpAddress, a.Hash)).ToListAsync(ct);
        return new PagedResult<AuditEntryDto>(items, page, pageSize, total);
    }

    /// <summary>Recorre la cadena completa y detecta cualquier registro alterado, insertado o eliminado.</summary>
    public async Task<AuditVerificationDto> VerifyAsync(Actor actor, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        return await VerifyChainAsync(db, clock, ct);
    }

    internal static async Task<AuditVerificationDto> VerifyChainAsync(ITimeFlowDbContext db, LocalClock clock, CancellationToken ct)
    {
        var previous = "";
        long count = 0;
        await foreach (var entry in db.AuditLogs.AsNoTracking().OrderBy(a => a.Sequence).AsAsyncEnumerable().WithCancellation(ct))
        {
            count++;
            if (entry.PreviousHash != previous || AuditHasher.Compute(entry) != entry.Hash)
                return new AuditVerificationDto(false, count, entry.Id, $"Se detectó una alteración en el registro #{entry.Id}.", clock.UtcNow);
            previous = entry.Hash;
        }
        return new AuditVerificationDto(true, count, null, $"Cadena íntegra: {count} registros verificados.", clock.UtcNow);
    }
}

public sealed class EmailMonitorService(ITimeFlowDbContext db, ActorGuard guard, AuditWriter audit, LocalClock clock)
{
    public async Task<PagedResult<EmailOutboxDto>> ListAsync(Actor actor, EmailStatus? status, int page, int pageSize, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var q = db.EmailOutbox.AsNoTracking();
        if (status is EmailStatus s) q = q.Where(m => m.Status == s);
        var total = await q.CountAsync(ct);
        pageSize = Math.Clamp(pageSize, 1, 200);
        var items = await q.OrderByDescending(m => m.CreatedAtUtc).Skip((Math.Max(1, page) - 1) * pageSize).Take(pageSize).ToListAsync(ct);
        return new PagedResult<EmailOutboxDto>(items.Select(m => new EmailOutboxDto(m.Id, m.ToAddresses, m.Subject, m.EventType, m.Status, Labels.EmailStatus(m.Status),
            m.Attempts, m.CreatedAtUtc, m.SentAtUtc, m.LastError, m.Folio, m.Provider)).ToList(), page, pageSize, total);
    }

    public async Task<string?> PreviewHtmlAsync(Actor actor, Guid id, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        return await db.EmailOutbox.AsNoTracking().Where(m => m.Id == id).Select(m => m.HtmlBody).FirstOrDefaultAsync(ct);
    }

    public async Task RetryAsync(Actor actor, Guid id, CancellationToken ct = default)
    {
        await guard.RequireRoleAsync(actor, UserRole.ProductAdmin, ct);
        var m = await db.EmailOutbox.FirstOrDefaultAsync(x => x.Id == id, ct) ?? throw new NotFoundException();
        if (m.Status != EmailStatus.Failed) throw new ConflictException("Solo se pueden reintentar correos fallidos.");
        m.Status = EmailStatus.Pending; m.Attempts = 0; m.NextAttemptAtUtc = clock.UtcNow; m.ConcurrencyStamp = Guid.NewGuid();
        audit.Write(actor, "email.retry", nameof(EmailOutboxMessage), id.ToString());
        await db.SaveChangesAsync(ct);
    }
}
