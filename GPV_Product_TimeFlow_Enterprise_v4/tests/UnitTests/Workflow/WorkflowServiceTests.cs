using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Infrastructure.Seeding;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace GPV.ProductTimeFlow.UnitTests.Workflow;

/// <summary>Reglas de negocio y flujo de autorización contra SQLite real (una BD temporal por prueba).</summary>
public class WorkflowServiceTests : IAsyncLifetime
{
    private TestDatabase _db = null!;
    private Actor _ana = null!, _laura = null!, _carlos = null!, _sofia = null!, _admin = null!;

    public async Task InitializeAsync()
    {
        _db = await TestDatabase.CreateAsync();
        _ana = await _db.ActorAsync("ana.empleada");
        _laura = await _db.ActorAsync("laura.jefa");
        _carlos = await _db.ActorAsync("carlos.superior");
        _sofia = await _db.ActorAsync("registro.admin");
        _admin = await _db.ActorAsync("admin.producto");
    }

    public async Task DisposeAsync() => await _db.DisposeAsync();

    // ── Utilidades ──────────────────────────────────────────────────────────

    private DateOnly Today => _db.Clock.Today;

    private static DateOnly NextMonday(DateOnly from, int minDaysAhead)
    {
        var d = from.AddDays(minDaysAhead);
        while (d.DayOfWeek != DayOfWeek.Monday) d = d.AddDays(1);
        return d;
    }

    /// <summary>Primer lunes (≥ minDaysAhead) cuya semana laboral no tiene festivos.</summary>
    private async Task<DateOnly> CleanMondayAsync(int minDaysAhead)
    {
        var cal = await _db.RunAsync(sp => sp.GetRequiredService<SettingsService>().GetCalendarAsync());
        var d = NextMonday(Today, minDaysAhead);
        while (cal.CountWorkingDays(d, d.AddDays(4)) != 5) d = d.AddDays(7);
        return d;
    }

    private RequestInput Overtime(DateOnly date, int startHour = 18, int hours = 2) => new()
    {
        Kind = RequestKind.Overtime, StartDate = date, StartTime = new TimeOnly(startHour, 0), EndTime = new TimeOnly((startHour + hours) % 24, 0),
        Reason = "Cierre de entregables del sprint", Project = "Plataforma de configuración", Activity = "Pruebas de regresión y documentación"
    };

    private Task<T> Wf<T>(Func<WorkflowService, Task<T>> f) => _db.RunAsync(sp => f(sp.GetRequiredService<WorkflowService>()));
    private Task Wf(Func<WorkflowService, Task> f) => _db.RunAsync(sp => f(sp.GetRequiredService<WorkflowService>()));

    private Task<Guid> CreateAsync(RequestInput input, Actor? who = null) => Wf(w => w.CreateDraftAsync(who ?? _ana, input));

    private Task<WorkflowResultDto> SubmitAsync(Guid id, Actor? who = null, string? signature = null) =>
        Wf(w => w.SubmitAsync(who ?? _ana, id, new SubmitInput { IdempotencyKey = Guid.NewGuid().ToString("N"), SignaturePngBase64 = signature }));

    private static DecisionInput Approve(int version = 1, int seed = 1, string? key = null) => new()
    {
        Decision = ApprovalDecisionType.Approve, SignaturePngBase64 = SyntheticSignature.Base64(seed), SignatureConsent = true,
        ExpectedVersion = version, IdempotencyKey = key ?? Guid.NewGuid().ToString("N")
    };

    private static DecisionInput Deny(ApprovalDecisionType type, string comment, int version = 1) => new()
    {
        Decision = type, Comment = comment, ExpectedVersion = version, IdempotencyKey = Guid.NewGuid().ToString("N")
    };

    private Task<WorkflowResultDto> DecideAsync(Actor who, Guid id, DecisionInput input) => Wf(w => w.DecideAsync(who, id, input));

    private Task<Request> LoadAsync(Guid id) => _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().Requests.AsNoTracking()
        .Include(r => r.Signatures).Include(r => r.Steps).Include(r => r.Decisions).SingleAsync(r => r.Id == id));

    private async Task<Guid> SubmittedOvertimeAsync(DateOnly date)
    {
        var id = await CreateAsync(Overtime(date));
        await SubmitAsync(id);
        return id;
    }

    // ── Reglas de captura ───────────────────────────────────────────────────

    [Fact]
    public async Task Duplicate_overtime_for_same_slot_is_rejected()
    {
        var date = Today.AddDays(-2);
        await SubmittedOvertimeAsync(date);

        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(Overtime(date)));
        Assert.Contains(ex.Errors, e => e.Contains("traslapa"));
    }

    [Fact]
    public async Task Overlapping_overtime_is_rejected_but_adjacent_is_allowed()
    {
        var date = Today.AddDays(-3);
        await SubmittedOvertimeAsync(date); // 18:00–20:00

        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(Overtime(date, startHour: 19, hours: 2)));
        Assert.Contains(ex.Errors, e => e.Contains("traslapa"));

        var adjacent = await CreateAsync(Overtime(date, startHour: 20, hours: 1)); // 20:00–21:00 contiguo
        Assert.NotEqual(Guid.Empty, adjacent);
    }

    [Fact]
    public async Task Overtime_crossing_midnight_overlaps_next_day_early_slot()
    {
        var date = Today.AddDays(-5);
        await SubmittedOvertimeAsync(date); // 18:00–20:00 del mismo día
        var crossing = await CreateAsync(Overtime(date, startHour: 22, hours: 3)); // 22:00–01:00
        await SubmitAsync(crossing);

        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(Overtime(date.AddDays(1), startHour: 0, hours: 2)));
        Assert.Contains(ex.Errors, e => e.Contains("traslapa"));
    }

    [Fact]
    public async Task Draft_overtime_does_not_block_calendar()
    {
        var date = Today.AddDays(-4);
        await CreateAsync(Overtime(date)); // sigue en borrador
        var second = await CreateAsync(Overtime(date));
        Assert.NotEqual(Guid.Empty, second);
    }

    [Fact]
    public async Task Overtime_with_equal_start_and_end_is_rejected()
    {
        var input = Overtime(Today);
        input.EndTime = input.StartTime;
        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(input));
        Assert.Contains(ex.Errors, e => e.Contains("no pueden ser iguales"));
    }

    [Fact]
    public async Task Overtime_older_than_30_days_is_rejected()
    {
        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(Overtime(Today.AddDays(-31))));
        Assert.Contains(ex.Errors, e => e.Contains("30 días"));
        Assert.NotEqual(Guid.Empty, await CreateAsync(Overtime(Today.AddDays(-30))));
    }

    [Fact]
    public async Task Vacation_with_insufficient_balance_is_rejected()
    {
        var start = await CleanMondayAsync(7);
        var input = new RequestInput { Kind = RequestKind.Vacation, StartDate = start, EndDate = start.AddDays(25), Reason = "Viaje largo al extranjero" };
        var available = await _db.RunAsync(sp => sp.GetRequiredService<RequestRules>().AvailableVacationDaysAsync(_ana.EmployeeId, start.Year, null, default));
        var cal = await _db.RunAsync(sp => sp.GetRequiredService<SettingsService>().GetCalendarAsync());
        var days = cal.CountWorkingDays(start, start.AddDays(25));
        Assert.True(days > available && days <= 20, $"Precondición: {days} días hábiles vs saldo {available}");

        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(input));
        Assert.Contains(ex.Errors, e => e.Contains("Saldo insuficiente"));
    }

    [Fact]
    public async Task Vacation_in_the_past_or_over_weekend_only_is_rejected()
    {
        var saturday = Today.AddDays(1);
        while (saturday.DayOfWeek != DayOfWeek.Saturday) saturday = saturday.AddDays(1);
        var weekend = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(new RequestInput
            { Kind = RequestKind.Vacation, StartDate = saturday, EndDate = saturday.AddDays(1), Reason = "Fin de semana largo" }));
        Assert.Contains(weekend.Errors, e => e.Contains("no contiene días hábiles"));

        var past = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(new RequestInput
            { Kind = RequestKind.Vacation, StartDate = Today.AddDays(-1), EndDate = Today.AddDays(2), Reason = "Vacaciones pasadas" }));
        Assert.Contains(past.Errors, e => e.Contains("a partir de hoy"));
    }

    [Fact]
    public async Task Unpaid_leave_requires_justification_and_category()
    {
        var start = await CleanMondayAsync(3);
        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(new RequestInput
        {
            Kind = RequestKind.UnpaidLeave, StartDate = start, EndDate = start, IsFullDay = true, Reason = "Asunto personal urgente"
        }));
        Assert.Contains(ex.Errors, e => e.Contains("justificación es obligatoria"));
        Assert.Contains(ex.Errors, e => e.Contains("clasificación"));

        // Categoría de otro tipo (permiso con goce) no es válida para permiso sin goce.
        var paidCategory = await _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().LeaveCategories.Where(c => c.AppliesTo == RequestKind.PaidLeave).Select(c => c.Id).FirstAsync());
        var wrongCat = await Assert.ThrowsAsync<BusinessRuleException>(() => CreateAsync(new RequestInput
        {
            Kind = RequestKind.UnpaidLeave, StartDate = start, EndDate = start, IsFullDay = true, Reason = "Asunto personal urgente",
            Justification = "Trámite familiar fuera de la ciudad.", LeaveCategoryId = paidCategory
        }));
        Assert.Contains(wrongCat.Errors, e => e.Contains("clasificación seleccionada no es válida"));

        var unpaidCategory = await _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().LeaveCategories.Where(c => c.AppliesTo == RequestKind.UnpaidLeave).Select(c => c.Id).FirstAsync());
        var ok = await CreateAsync(new RequestInput
        {
            Kind = RequestKind.UnpaidLeave, StartDate = start, EndDate = start, IsFullDay = true, Reason = "Asunto personal urgente",
            Justification = "Trámite familiar fuera de la ciudad.", LeaveCategoryId = unpaidCategory
        });
        Assert.NotEqual(Guid.Empty, ok);
    }

    // ── Autorización ────────────────────────────────────────────────────────

    [Fact]
    public async Task Requester_cannot_decide_own_request()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        await Assert.ThrowsAsync<ForbiddenException>(() => DecideAsync(_ana, id, Approve()));
        Assert.Equal(RequestStatus.PendingSupervisor, (await LoadAsync(id)).Status);
    }

    [Fact]
    public async Task Hierarchy_where_employee_is_own_supervisor_cannot_submit()
    {
        await _db.RunAsync(async sp =>
        {
            var db = sp.GetRequiredService<ITimeFlowDbContext>();
            var h = await db.ReportingHierarchy.SingleAsync(x => x.EmployeeId == _ana.EmployeeId && x.IsCurrent);
            h.DirectSupervisorId = _ana.EmployeeId;
            await db.SaveChangesAsync();
        });
        var id = await CreateAsync(Overtime(Today.AddDays(-1)));
        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => SubmitAsync(id));
        Assert.Contains(ex.Errors, e => e.Contains("nadie puede autorizar sus propias solicitudes"));
    }

    [Fact]
    public async Task Manager_cannot_decide_while_pending_supervisor_and_outsider_is_hidden()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        await Assert.ThrowsAsync<ConflictException>(() => DecideAsync(_carlos, id, Approve()));
        await Assert.ThrowsAsync<NotFoundException>(() => DecideAsync(_sofia, id, Approve()));
    }

    [Fact]
    public async Task Approval_requires_signature_and_consent()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));

        var noSig = Approve();
        noSig.SignaturePngBase64 = null;
        var e1 = await Assert.ThrowsAsync<BusinessRuleException>(() => DecideAsync(_laura, id, noSig));
        Assert.Contains(e1.Errors, e => e.Contains("necesario firmar"));

        var noConsent = Approve();
        noConsent.SignatureConsent = false;
        var e2 = await Assert.ThrowsAsync<BusinessRuleException>(() => DecideAsync(_laura, id, noConsent));
        Assert.Contains(e2.Errors, e => e.Contains("confirmar expresamente"));

        var tiny = Approve();
        tiny.SignaturePngBase64 = Convert.ToBase64String(new byte[] { 0x89, 0x50, 0x4E, 0x47, 1, 2, 3, 4, 5 });
        var e3 = await Assert.ThrowsAsync<BusinessRuleException>(() => DecideAsync(_laura, id, tiny));
        Assert.Contains("vacía", e3.Message);

        Assert.Equal(RequestStatus.PendingSupervisor, (await LoadAsync(id)).Status);
        var ok = await DecideAsync(_laura, id, Approve());
        Assert.Equal(RequestStatus.PendingManager, ok.Status);
    }

    [Fact]
    public async Task Reject_requires_comment_of_at_least_10_chars()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        var ex = await Assert.ThrowsAsync<BusinessRuleException>(() => DecideAsync(_laura, id, Deny(ApprovalDecisionType.Reject, "corto")));
        Assert.Contains(ex.Errors, e => e.Contains("mínimo 10 caracteres"));
        await Assert.ThrowsAsync<BusinessRuleException>(() => DecideAsync(_laura, id, Deny(ApprovalDecisionType.Return, "         ")));

        var ok = await DecideAsync(_laura, id, Deny(ApprovalDecisionType.Reject, "No corresponde a la planeación."));
        Assert.Equal(RequestStatus.SupervisorRejected, ok.Status);
        var r = await LoadAsync(id);
        Assert.NotNull(r.ClosedAtUtc);
        Assert.Empty(r.Signatures);
    }

    [Fact]
    public async Task Expected_version_mismatch_is_a_conflict()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        await Assert.ThrowsAsync<ConflictException>(() => DecideAsync(_laura, id, Approve(version: 2)));
        Assert.Equal(RequestStatus.PendingSupervisor, (await LoadAsync(id)).Status);
    }

    [Fact]
    public async Task Resubmission_after_return_increments_version_and_invalidates_previous_signatures()
    {
        var id = await CreateAsync(Overtime(Today.AddDays(-1)));
        await SubmitAsync(id, signature: SyntheticSignature.Base64(10));
        await DecideAsync(_laura, id, Approve(seed: 11));
        var returned = await DecideAsync(_carlos, id, Deny(ApprovalDecisionType.Return, "Precisa el proyecto y la actividad realizada."));
        Assert.Equal(RequestStatus.ReturnedForCorrection, returned.Status);

        var before = await LoadAsync(id);
        Assert.Equal(1, before.Version);
        Assert.Equal(2, before.Signatures.Count(s => s.IsValid));
        Assert.Equal("Precisa el proyecto y la actividad realizada.", before.LastReturnComment);

        // Corrige y reenvía.
        var corrected = Overtime(Today.AddDays(-1));
        corrected.Activity = "Pruebas de regresión del módulo de configuración";
        await Wf(w => w.UpdateDraftAsync(_ana, id, corrected));
        var afterEdit = await LoadAsync(id);
        Assert.Equal(2, afterEdit.Version); // el cambio sustancial con firmas vigentes sube la versión
        Assert.All(afterEdit.Signatures, s => Assert.False(s.IsValid));

        var res = await SubmitAsync(id);
        Assert.Equal(RequestStatus.PendingSupervisor, res.Status);
        var after = await LoadAsync(id);
        Assert.Equal(2, after.Version); // la edición ya generó la nueva versión; el reenvío no la duplica
        Assert.All(after.Signatures, s => { Assert.False(s.IsValid); Assert.NotNull(s.InvalidatedAtUtc); Assert.False(string.IsNullOrEmpty(s.InvalidationReason)); });
        Assert.Contains(after.Steps, s => s.RequestVersion == 2 && s.Type == ApprovalStepType.DirectSupervisor && s.Status == ApprovalStepStatus.Pending);
        Assert.Null(after.LastReturnComment);

        // La decisión con la versión anterior se rechaza; con la vigente procede.
        await Assert.ThrowsAsync<ConflictException>(() => DecideAsync(_laura, id, Approve(version: 1)));
        var ok = await DecideAsync(_laura, id, Approve(version: 2, seed: 12));
        Assert.Equal(RequestStatus.PendingManager, ok.Status);
        var final = await LoadAsync(id);
        Assert.Single(final.Signatures, s => s.IsValid && s.RequestVersion == 2);
    }

    [Fact]
    public async Task Resubmission_without_edit_also_increments_version_and_invalidates_signatures()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        await DecideAsync(_laura, id, Approve());
        await DecideAsync(_carlos, id, Deny(ApprovalDecisionType.Return, "Favor de revisar las horas registradas."));
        var res = await SubmitAsync(id);
        Assert.Equal(RequestStatus.PendingSupervisor, res.Status);
        var r = await LoadAsync(id);
        Assert.Equal(2, r.Version);
        var sig = Assert.Single(r.Signatures);
        Assert.False(sig.IsValid);
    }

    [Fact]
    public async Task Vacation_is_consumed_exactly_once_after_manager_approval()
    {
        var start = await CleanMondayAsync(7);
        var id = await CreateAsync(new RequestInput { Kind = RequestKind.Vacation, StartDate = start, EndDate = start.AddDays(1), Reason = "Vacaciones familiares" });
        await SubmitAsync(id);
        var key = $"consume:{id:N}";
        async Task<int> CountAsync() => await _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().VacationTransactions.CountAsync(t => t.DeduplicationKey == key));

        await DecideAsync(_laura, id, Approve());
        Assert.Equal(0, await CountAsync()); // la jefa directa no descuenta

        var managerKey = Guid.NewGuid().ToString("N");
        var res = await DecideAsync(_carlos, id, Approve(seed: 2, key: managerKey));
        Assert.Equal(RequestStatus.PendingAdministrativeRegistration, res.Status);
        Assert.Equal(1, await CountAsync());

        // Reintento idempotente (doble clic) no descuenta de nuevo.
        var dup = await DecideAsync(_carlos, id, Approve(seed: 2, key: managerKey));
        Assert.True(dup.WasDuplicate);
        // Las acciones administrativas tampoco.
        await Wf(w => w.AdministrativeAsync(_sofia, id, new AdministrativeInput { Action = AdministrativeAction.Register }));
        await Wf(w => w.AdministrativeAsync(_sofia, id, new AdministrativeInput { Action = AdministrativeAction.Complete }));
        Assert.Equal(1, await CountAsync());

        var tx = await _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().VacationTransactions.AsNoTracking().SingleAsync(t => t.DeduplicationKey == key));
        Assert.Equal(-2m, tx.Days);
        Assert.Equal(VacationTransactionType.Consumption, tx.Type);
    }

    [Fact]
    public async Task Folio_sequence_is_unique_and_incrementing()
    {
        var ids = new List<Guid>();
        for (var i = 0; i < 4; i++) ids.Add(await CreateAsync(Overtime(Today.AddDays(-1 - i))));

        var folios = await _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().Requests.AsNoTracking()
            .Where(r => ids.Contains(r.Id)).OrderBy(r => r.Folio).Select(r => r.Folio).ToListAsync());
        var year = Today.Year;
        Assert.Equal(Enumerable.Range(1, 4).Select(n => FolioFormatter.Format(year, n)), folios);
        Assert.All(folios, f => Assert.True(FolioFormatter.IsValid(f)));

        var seq = await _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().FolioSequences.AsNoTracking().SingleAsync(s => s.Year == year));
        Assert.Equal(4, seq.LastValue);
    }

    [Fact]
    public async Task Audit_chain_verifies_after_full_flow_and_fails_after_tampering()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        await DecideAsync(_laura, id, Approve());
        await DecideAsync(_carlos, id, Approve(seed: 2));
        await Wf(w => w.AdministrativeAsync(_sofia, id, new AdministrativeInput { Action = AdministrativeAction.Receive }));
        await Wf(w => w.AdministrativeAsync(_sofia, id, new AdministrativeInput { Action = AdministrativeAction.Register, ExternalReference = "REG-001" }));
        var done = await Wf(w => w.AdministrativeAsync(_sofia, id, new AdministrativeInput { Action = AdministrativeAction.Complete }));
        Assert.Equal(RequestStatus.Completed, done.Status);

        Task<AuditVerificationDto> VerifyAsync() => _db.RunAsync(sp => sp.GetRequiredService<AuditService>().VerifyAsync(_admin));
        var ok = await VerifyAsync();
        Assert.True(ok.IsValid, ok.Message);
        Assert.True(ok.EntriesChecked > 5);

        // Solo el administrador de Producto puede verificar.
        await Assert.ThrowsAsync<ForbiddenException>(() => _db.RunAsync(sp => sp.GetRequiredService<AuditService>().VerifyAsync(_sofia)));

        var (targetSeq, targetId) = await _db.RunAsync(async sp =>
        {
            var db = sp.GetRequiredService<ITimeFlowDbContext>();
            var row = await db.AuditLogs.AsNoTracking().Where(a => a.EntityId == id.ToString()).OrderBy(a => a.Sequence).Select(a => new { a.Sequence, a.Id }).FirstAsync();
            return (row.Sequence, row.Id);
        });
        await _db.RunAsync(sp => sp.GetRequiredService<ITimeFlowDbContext>().Database
            .ExecuteSqlRawAsync("UPDATE AuditLogs SET Details = 'x' WHERE Sequence = {0}", targetSeq));

        var broken = await VerifyAsync();
        Assert.False(broken.IsValid);
        Assert.Equal(targetId, broken.FirstBrokenEntryId);
    }

    [Fact]
    public async Task Immutable_entities_cannot_be_modified_through_ef()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        await Assert.ThrowsAsync<InvalidOperationException>(() => _db.RunAsync(async sp =>
        {
            var db = sp.GetRequiredService<ITimeFlowDbContext>();
            var d = await db.ApprovalDecisions.FirstAsync(x => x.RequestId == id);
            d.Comment = "alterado";
            await db.SaveChangesAsync();
        }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => _db.RunAsync(async sp =>
        {
            var db = sp.GetRequiredService<ITimeFlowDbContext>();
            var a = await db.AuditLogs.OrderByDescending(x => x.Sequence).FirstAsync();
            db.AuditLogs.Remove(a);
            await db.SaveChangesAsync();
        }));
    }

    [Fact]
    public async Task Cancel_is_only_allowed_to_requester_and_before_final_decision()
    {
        var id = await SubmittedOvertimeAsync(Today.AddDays(-1));
        await Assert.ThrowsAsync<ForbiddenException>(() => Wf(w => w.CancelAsync(_laura, id, new CancelInput())));
        var res = await Wf(w => w.CancelAsync(_ana, id, new CancelInput { Reason = "Ya no es necesario" }));
        Assert.Equal(RequestStatus.Cancelled, res.Status);
        var again = await Wf(w => w.CancelAsync(_ana, id, new CancelInput()));
        Assert.True(again.WasDuplicate);
        await Assert.ThrowsAsync<ConflictException>(() => DecideAsync(_laura, id, Approve()));

        var id2 = await SubmittedOvertimeAsync(Today.AddDays(-2));
        await DecideAsync(_laura, id2, Approve());
        await DecideAsync(_carlos, id2, Approve(seed: 2));
        await Assert.ThrowsAsync<ConflictException>(() => Wf(w => w.CancelAsync(_ana, id2, new CancelInput())));
    }
}
