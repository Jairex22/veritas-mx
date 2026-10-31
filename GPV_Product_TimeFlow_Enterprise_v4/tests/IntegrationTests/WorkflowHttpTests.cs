using System.Net;
using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Infrastructure.Email;
using GPV.ProductTimeFlow.Infrastructure.Seeding;
using GPV.ProductTimeFlow.IntegrationTests.Infrastructure;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace GPV.ProductTimeFlow.IntegrationTests;

/// <summary>Flujo completo EMPLEADO → JEFA DIRECTA → JEFE SUPERIOR → REGISTRO ADMINISTRATIVO sobre HTTP.</summary>
public class WorkflowHttpTests(TimeFlowApiFactory factory) : IClassFixture<TimeFlowApiFactory>
{
    private static string Key() => Guid.NewGuid().ToString("N");

    private static DecisionInput Approve(int version, int seed) => new()
    {
        Decision = ApprovalDecisionType.Approve, SignaturePngBase64 = SyntheticSignature.Base64(seed), SignatureConsent = true,
        ExpectedVersion = version, IdempotencyKey = Key()
    };

    private static DecisionInput Deny(ApprovalDecisionType type, string comment, int version) => new()
    {
        Decision = type, Comment = comment, ExpectedVersion = version, IdempotencyKey = Key()
    };

    private async Task<(TimeFlowApiClient Ana, RequestDetailDto Request)> SubmittedOvertimeAsync(string? employeeSignature = null)
    {
        var ana = await factory.LoginAsync(TimeFlowApiFactory.Ana);
        var draft = await ana.CreateRequestAsync(TimeFlowApiFactory.Overtime(factory.NextOvertimeDate()));
        Assert.Equal(RequestStatus.Draft, draft.Summary.Status);
        var submitted = await ana.SubmitAsync(draft.Summary.Id, new SubmitInput { IdempotencyKey = Key(), SignaturePngBase64 = employeeSignature });
        Assert.Equal(RequestStatus.PendingSupervisor, submitted.Status);
        return (ana, await ana.GetRequestAsync(draft.Summary.Id));
    }

    private async Task<(TimeFlowApiClient Ana, Guid Id, string Folio)> CompletedOvertimeAsync()
    {
        var (ana, req) = await SubmittedOvertimeAsync();
        var id = req.Summary.Id;
        var laura = await factory.LoginAsync(TimeFlowApiFactory.Laura);
        var carlos = await factory.LoginAsync(TimeFlowApiFactory.Carlos);
        var sofia = await factory.LoginAsync(TimeFlowApiFactory.Sofia);

        Assert.Equal(RequestStatus.PendingManager, (await laura.DecideAsync(id, Approve(1, 1))).Status);
        Assert.Equal(RequestStatus.PendingAdministrativeRegistration, (await carlos.DecideAsync(id, Approve(1, 2))).Status);
        Assert.Equal(RequestStatus.PendingAdministrativeRegistration, (await sofia.AdministrativeAsync(id, new AdministrativeInput { Action = AdministrativeAction.Receive })).Status);
        Assert.Equal(RequestStatus.AdministrativeRegistered, (await sofia.AdministrativeAsync(id, new AdministrativeInput { Action = AdministrativeAction.Register, ExternalReference = "REG-0001" })).Status);
        Assert.Equal(RequestStatus.Completed, (await sofia.AdministrativeAsync(id, new AdministrativeInput { Action = AdministrativeAction.Complete })).Status);
        return (ana, id, req.Summary.Folio);
    }

    [Fact]
    public async Task Happy_path_completes_and_produces_export_and_emails()
    {
        var (ana, id, folio) = await CompletedOvertimeAsync();

        // Ana ve su solicitud completada con firmas válidas de ambos filtros.
        var detail = await ana.GetRequestAsync(id);
        Assert.Equal(RequestStatus.Completed, detail.Summary.Status);
        Assert.Equal(2, detail.Signatures.Count(s => s.IsValid));
        Assert.Contains(detail.Steps, s => s.Type == ApprovalStepType.DirectSupervisor && s.Status == ApprovalStepStatus.Approved);
        Assert.Contains(detail.Steps, s => s.Type == ApprovalStepType.SeniorManager && s.Status == ApprovalStepStatus.Approved);
        Assert.Contains(detail.Steps, s => s.Type == ApprovalStepType.AdministrativeRegistration && s.Status == ApprovalStepStatus.Registered);
        Assert.Equal("REG-0001", detail.Administrative!.ExternalReference);
        Assert.NotNull(detail.Administrative.ReceivedAtUtc);
        Assert.NotNull(detail.Administrative.ProcessedAtUtc);
        var mine = await ana.ListRequestsAsync(new RequestQuery { Scope = RequestScope.Mine, Status = RequestStatus.Completed });
        Assert.Contains(mine.Items, r => r.Id == id);

        // Exportación a Excel por registro administrativo.
        var sofia = await factory.LoginAsync(TimeFlowApiFactory.Sofia);
        var sofiaId = await factory.EmployeeIdAsync(TimeFlowApiFactory.Sofia);
        var exportsBefore = await factory.WithDbAsync(db => db.ExcelExports.CountAsync(x => x.ExportedByEmployeeId == sofiaId));
        var xlsx = await sofia.ExportExcelAsync(new ExportFilter { Set = "approved" });
        Assert.True(xlsx.Length > 1000);
        Assert.Equal(new byte[] { 0x50, 0x4B, 0x03, 0x04 }, xlsx[..4]);
        var exportLog = await factory.WithDbAsync(db => db.ExcelExports.Where(x => x.ExportedByEmployeeId == sofiaId).ToListAsync());
        Assert.Equal(exportsBefore + 1, exportLog.Count);
        Assert.Contains(exportLog, x => x.RowCount >= 1 && x.Sha256.Length == 64);

        // Un empleado sin rol de liderazgo no puede exportar.
        await ApiAssert.FailsWithAsync(HttpStatusCode.Forbidden, () => ana.ExportExcelAsync(new ExportFilter()));

        // Bandeja de correo (Outbox): un mensaje por evento.
        var events = await factory.WithDbAsync(db => db.EmailOutbox.Where(m => m.RequestId == id).Select(m => m.EventType).ToListAsync());
        Assert.Equal(["administrative-registered", "completed", "manager-approved", "submitted", "supervisor-approved"], events.Order().ToArray());

        // Procesar la cola con el proveedor Mock: MockDelivered (nunca Sent) y archivos HTML en mail-drop.
        var processor = factory.Services.GetRequiredService<EmailOutboxProcessor>();
        while (await processor.ProcessBatchAsync(CancellationToken.None) > 0) { }
        var messages = await factory.WithDbAsync(db => db.EmailOutbox.AsNoTracking().Where(m => m.RequestId == id).ToListAsync());
        Assert.All(messages, m =>
        {
            Assert.Equal(EmailStatus.MockDelivered, m.Status);
            Assert.NotEqual(EmailStatus.Sent, m.Status);
            Assert.Equal(1, m.Attempts);
            Assert.NotNull(m.SentAtUtc);
            Assert.StartsWith("[DEMO]", m.Subject);
        });
        var dropFolder = Path.Combine(factory.DataRoot, "mail-drop");
        var files = Directory.GetFiles(dropFolder, $"*_{folio}_*.html");
        Assert.Equal(5, files.Length);
        Assert.All(messages, m => Assert.Contains(files, f => Path.GetFileName(f) == m.ProviderMessageId));
        Assert.Contains(folio, await File.ReadAllTextAsync(files[0]));
    }

    [Fact]
    public async Task Pdf_of_completed_request_is_a_valid_pdf()
    {
        var (ana, id, _) = await CompletedOvertimeAsync();
        using var response = await ana.Http.GetAsync($"api/v1/requests/{id}/pdf");
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("application/pdf", response.Content.Headers.ContentType?.MediaType);
        var pdf = await response.Content.ReadAsByteArrayAsync();
        Assert.Equal("%PDF", System.Text.Encoding.ASCII.GetString(pdf, 0, 4));
        Assert.True(pdf.Length > 5 * 1024);
    }

    [Fact]
    public async Task Supervisor_reject_closes_request_and_manager_cannot_decide()
    {
        var (ana, req) = await SubmittedOvertimeAsync();
        var id = req.Summary.Id;
        var laura = await factory.LoginAsync(TimeFlowApiFactory.Laura);
        var carlos = await factory.LoginAsync(TimeFlowApiFactory.Carlos);

        var inbox = await laura.ListRequestsAsync(new RequestQuery { Scope = RequestScope.ApprovalInbox });
        Assert.Contains(inbox.Items, r => r.Id == id);

        await ApiAssert.FailsWithAsync(HttpStatusCode.UnprocessableEntity, () => laura.DecideAsync(id, Deny(ApprovalDecisionType.Reject, "corto", 1)));
        var res = await laura.DecideAsync(id, Deny(ApprovalDecisionType.Reject, "No corresponde a la planeación del área.", 1));
        Assert.Equal(RequestStatus.SupervisorRejected, res.Status);

        var ex = await Assert.ThrowsAsync<ApiException>(() => carlos.DecideAsync(id, Approve(1, 3)));
        Assert.Contains(ex.Status, new[] { HttpStatusCode.Conflict, HttpStatusCode.Forbidden });
        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => laura.DecideAsync(id, Approve(1, 3)));
        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => ana.SubmitAsync(id, new SubmitInput()));

        var detail = await ana.GetRequestAsync(id);
        Assert.Equal(RequestStatus.SupervisorRejected, detail.Summary.Status);
        Assert.Empty(detail.Signatures);
        Assert.False(detail.Permissions.CanCancel);
        var emails = await factory.WithDbAsync(db => db.EmailOutbox.Where(m => m.RequestId == id).Select(m => m.EventType).ToListAsync());
        Assert.Contains("supervisor-rejected", emails);
    }

    [Fact]
    public async Task Return_edit_and_resubmit_creates_new_version_and_invalidates_prior_signatures()
    {
        var (ana, req) = await SubmittedOvertimeAsync(employeeSignature: SyntheticSignature.Base64(20));
        var id = req.Summary.Id;
        Assert.Single(req.Signatures, s => s.IsValid && s.SignerRole == "Solicitante");
        var laura = await factory.LoginAsync(TimeFlowApiFactory.Laura);

        var returned = await laura.DecideAsync(id, Deny(ApprovalDecisionType.Return, "Detalla mejor la actividad realizada.", 1));
        Assert.Equal(RequestStatus.ReturnedForCorrection, returned.Status);
        var afterReturn = await ana.GetRequestAsync(id);
        Assert.Equal("Detalla mejor la actividad realizada.", afterReturn.ReturnComment);
        Assert.True(afterReturn.Permissions.CanEdit);

        var corrected = TimeFlowApiFactory.Overtime(afterReturn.Summary.StartDate);
        corrected.Activity = "Pruebas de regresión del módulo de configuración y reporte de defectos";
        var edited = await ana.UpdateRequestAsync(id, corrected);
        Assert.Equal(corrected.Activity, edited.Activity);

        var resubmitted = await ana.SubmitAsync(id, new SubmitInput { IdempotencyKey = Key() });
        Assert.Equal(RequestStatus.PendingSupervisor, resubmitted.Status);

        var v2 = await ana.GetRequestAsync(id);
        Assert.True(v2.Summary.Version >= 2, $"La versión debe incrementarse tras corrección y reenvío (actual {v2.Summary.Version}).");
        Assert.NotEqual(req.ContentHash, v2.ContentHash);
        var oldSignature = Assert.Single(v2.Signatures);
        Assert.False(oldSignature.IsValid);
        Assert.False(string.IsNullOrWhiteSpace(oldSignature.InvalidationReason));
        Assert.Equal(1, oldSignature.RequestVersion);

        // La jefa debe decidir sobre la versión vigente.
        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => laura.DecideAsync(id, Approve(1, 21)));
        var ok = await laura.DecideAsync(id, Approve(v2.Summary.Version, 21));
        Assert.Equal(RequestStatus.PendingManager, ok.Status);
    }

    [Fact]
    public async Task Manager_reject_is_final()
    {
        var (ana, req) = await SubmittedOvertimeAsync();
        var id = req.Summary.Id;
        var laura = await factory.LoginAsync(TimeFlowApiFactory.Laura);
        var carlos = await factory.LoginAsync(TimeFlowApiFactory.Carlos);
        await laura.DecideAsync(id, Approve(1, 30));

        var res = await carlos.DecideAsync(id, Deny(ApprovalDecisionType.Reject, "No es posible por cierre del trimestre.", 1));
        Assert.Equal(RequestStatus.ManagerRejected, res.Status);
        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => carlos.DecideAsync(id, Approve(1, 31)));
        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => ana.CancelAsync(id, new CancelInput()));

        var sofia = await factory.LoginAsync(TimeFlowApiFactory.Sofia);
        await ApiAssert.FailsWithAsync(HttpStatusCode.NotFound, () => sofia.GetRequestAsync(id));

        var detail = await ana.GetRequestAsync(id);
        Assert.Equal(RequestStatus.ManagerRejected, detail.Summary.Status);
        var emails = await factory.WithDbAsync(db => db.EmailOutbox.Where(m => m.RequestId == id).Select(m => m.EventType).ToListAsync());
        Assert.Contains("manager-rejected", emails);
    }

    [Fact]
    public async Task Cancel_pending_request_prevents_further_decisions()
    {
        var (ana, req) = await SubmittedOvertimeAsync();
        var id = req.Summary.Id;
        var laura = await factory.LoginAsync(TimeFlowApiFactory.Laura);

        await ApiAssert.FailsWithAsync(HttpStatusCode.Forbidden, () => laura.CancelAsync(id, new CancelInput { Reason = "Intento indebido" }));
        var res = await ana.CancelAsync(id, new CancelInput { Reason = "Se reprogramó la actividad" });
        Assert.Equal(RequestStatus.Cancelled, res.Status);
        Assert.False(res.WasDuplicate);

        await ApiAssert.FailsWithAsync(HttpStatusCode.Conflict, () => laura.DecideAsync(id, Approve(1, 40)));
        var again = await ana.CancelAsync(id, new CancelInput());
        Assert.True(again.WasDuplicate);
        Assert.Equal(RequestStatus.Cancelled, (await ana.GetRequestAsync(id)).Summary.Status);

        // Una solicitud cancelada no bloquea el calendario: se puede volver a capturar el mismo horario.
        var again2 = await ana.CreateRequestAsync(TimeFlowApiFactory.Overtime(req.Summary.StartDate));
        Assert.Equal(RequestStatus.Draft, again2.Summary.Status);
    }

    [Fact]
    public async Task Vacation_flow_consumes_balance_once()
    {
        var ana = await factory.LoginAsync(TimeFlowApiFactory.Ana);
        var start = TimeFlowApiFactory.TodayMexico.AddDays(60);
        while (start.DayOfWeek != DayOfWeek.Tuesday) start = start.AddDays(1);
        var preview = await ana.VacationPreviewAsync(new VacationPreviewRequest { StartDate = start, EndDate = start.AddDays(1) });
        var balanceBefore = await ana.VacationBalanceAsync();

        var draft = await ana.CreateRequestAsync(new RequestInput { Kind = RequestKind.Vacation, StartDate = start, EndDate = start.AddDays(1), Reason = "Vacaciones familiares" });
        Assert.Equal(preview.BusinessDays, draft.Summary.Days);
        var id = draft.Summary.Id;
        await ana.SubmitAsync(id, new SubmitInput { IdempotencyKey = Key() });
        await (await factory.LoginAsync(TimeFlowApiFactory.Laura)).DecideAsync(id, Approve(1, 50));
        var carlos = await factory.LoginAsync(TimeFlowApiFactory.Carlos);
        var approve = Approve(1, 51);
        await carlos.DecideAsync(id, approve);
        Assert.True((await carlos.DecideAsync(id, approve)).WasDuplicate);

        var key = $"consume:{id:N}";
        Assert.Equal(1, await factory.WithDbAsync(db => db.VacationTransactions.CountAsync(t => t.DeduplicationKey == key)));
        if (start.Year == TimeFlowApiFactory.TodayMexico.Year)
        {
            var after = await ana.VacationBalanceAsync();
            Assert.Equal(balanceBefore.Available - draft.Summary.Days, after.Available);
        }
    }
}
