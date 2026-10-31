using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;

namespace GPV.ProductTimeFlow.Application;

/// <summary>
/// Servicio de dominio del flujo de autorización. Cada acción sigue el mismo protocolo:
/// 1) identidad, 2) permisos, 3) estado, 4) reglas, 5) transición atómica, 6) auditoría,
/// 7) notificación pendiente (outbox), 8) confirmación, 9) aviso en tiempo real para actualizar la interfaz.
/// </summary>
public sealed class WorkflowService(
    ITimeFlowDbContext db,
    ActorGuard guard,
    RequestRules rules,
    SettingsService settings,
    AuditWriter audit,
    NotificationDispatcher notifications,
    IFileStorage storage,
    LocalClock clock,
    IOptions<TimeFlowOptions> options,
    ILogger<WorkflowService> logger)
{
    private static readonly HashSet<string> AllowedExtensions = [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"];
    private const int MaxSignatureBytes = 400 * 1024;

    // ── Borradores ───────────────────────────────────────────────────────────

    public async Task<Guid> CreateDraftAsync(Actor actor, RequestInput input, CancellationToken ct = default)
    {
        var employee = await guard.RequireActiveAsync(actor, ct);
        var computed = await rules.ValidateAsync(employee, input, null, ct);
        var type = await db.RequestTypes.FirstOrDefaultAsync(t => t.Kind == input.Kind && t.IsActive, ct)
            ?? throw new BusinessRuleException("El tipo de solicitud no está habilitado.");

        var request = new Request
        {
            Id = Guid.NewGuid(),
            EmployeeId = employee.Id,
            Employee = employee,
            RequestTypeId = type.Id,
            Kind = input.Kind,
            Status = RequestStatus.Draft,
            StatusChangedAtUtc = clock.UtcNow
        };
        Apply(request, input, computed);

        await AtomicAsync(async () =>
        {
            request.Folio = await NextFolioAsync(ct);
            request.ContentHash = RequestContentHasher.Compute(request);
            db.Requests.Add(request);
            audit.Write(actor, "request.created", nameof(Request), request.Id.ToString(), new { request.Folio, Kind = request.Kind.ToString() });
        }, ct);
        return request.Id;
    }

    public async Task UpdateDraftAsync(Actor actor, Guid id, RequestInput input, CancellationToken ct = default)
    {
        var employee = await guard.RequireActiveAsync(actor, ct);
        var request = await LoadForCommandAsync(id, actor, ct);
        if (request.EmployeeId != actor.EmployeeId) throw new ForbiddenException("Solo el solicitante puede modificar la solicitud.");
        if (!request.IsEditable) throw new ConflictException($"No se puede editar una solicitud en estado «{Labels.Status(request.Status)}».");
        if (request.Kind != input.Kind) throw new BusinessRuleException("No se puede cambiar el tipo de una solicitud existente. Cancele y cree una nueva.");

        var computed = await rules.ValidateAsync(employee, input, request.Id, ct);
        await AtomicAsync(() =>
        {
            var before = request.ContentHash;
            Apply(request, input, computed);
            RefreshContentHash(request, before, actor, "Cambio sustancial posterior a la firma: se requiere nueva revisión.");
            audit.Write(actor, "request.updated", nameof(Request), request.Id.ToString(), new { request.Folio, request.Version });
            return Task.CompletedTask;
        }, ct);
    }

    // ── Envío ────────────────────────────────────────────────────────────────

    public async Task<WorkflowResultDto> SubmitAsync(Actor actor, Guid id, SubmitInput input, CancellationToken ct = default)
    {
        var employee = await guard.RequireActiveAsync(actor, ct);
        var request = await LoadForCommandAsync(id, actor, ct);
        if (request.EmployeeId != actor.EmployeeId) throw new ForbiddenException("Solo el solicitante puede enviar la solicitud.");
        if (Duplicate(request, input.IdempotencyKey, actor) is { } dup) return dup;
        if (!RequestStateMachine.CanApply(request.Status, WorkflowAction.Submit))
            throw new ConflictException($"La solicitud ya fue enviada (estado actual: {Labels.Status(request.Status)}).");

        // Reglas: se revalida todo con datos actuales (saldo, traslapes, límites).
        await rules.ValidateAsync(employee, ToInput(request), request.Id, ct);
        var policy = await settings.GetPolicyAsync(ct);
        if (request.LeaveCategory?.RequiresAttachment == true && !request.Attachments.Any(a => !a.IsDeleted))
            throw new BusinessRuleException($"La clasificación «{request.LeaveCategory.Name}» requiere adjuntar un documento.");
        byte[]? signature = null;
        if (!string.IsNullOrWhiteSpace(input.SignaturePngBase64)) signature = DecodeSignature(input.SignaturePngBase64);
        else if (policy.RequireEmployeeSignature) throw new BusinessRuleException("La política vigente requiere la firma del solicitante.");

        var hierarchy = await db.CurrentAsync(employee.Id, ct);
        var supervisor = hierarchy?.DirectSupervisor;
        var manager = hierarchy?.SeniorManager;
        var hierarchyErrors = new List<string>();
        if (supervisor is null || !supervisor.IsActive) hierarchyErrors.Add("No tienes una jefa directa activa asignada. Contacta al administrador de Producto.");
        if (manager is null || !manager.IsActive) hierarchyErrors.Add("No tienes un jefe superior activo asignado. Contacta al administrador de Producto.");
        if (supervisor?.Id == employee.Id || manager?.Id == employee.Id) hierarchyErrors.Add("La jerarquía es inválida: nadie puede autorizar sus propias solicitudes.");
        if (supervisor is not null && supervisor.Id == manager?.Id) hierarchyErrors.Add("La jefa directa y el jefe superior deben ser personas distintas (dos filtros independientes).");
        if (hierarchyErrors.Count > 0) throw new BusinessRuleException(hierarchyErrors);

        await AtomicAsync(async () =>
        {
            var now = clock.UtcNow;
            var resubmission = request.Steps.Count > 0;
            if (resubmission)
            {
                // Cada reenvío es una nueva versión revisable: las autorizaciones previas dejan de valer.
                // Si el empleado ya editó (la edición subió la versión), no se incrementa de nuevo.
                if (request.Steps.Any(s => s.RequestVersion == request.Version)) request.Version++;
                InvalidateSignatures(request, "Solicitud reenviada: requiere nueva revisión completa.");
                foreach (var s in request.Steps.Where(s => s.Status is ApprovalStepStatus.Pending or ApprovalStepStatus.Waiting))
                    s.Status = ApprovalStepStatus.Invalidated;
            }
            request.AssignedSupervisorId = supervisor!.Id;
            request.AssignedSupervisor = supervisor;
            request.AssignedManagerId = manager!.Id;
            request.AssignedManager = manager;
            request.SubmittedAtUtc = now;
            request.LastReturnComment = null;
            request.ContentHash = RequestContentHasher.Compute(request);

            Record(request, WorkflowAction.Submit, actor, null, input.IdempotencyKey, null);
            Record(request, WorkflowAction.RouteToSupervisor, Actor.System, null, null, null);

            request.Steps.Add(NewStep(request, 1, ApprovalStepType.DirectSupervisor, supervisor.Id, ApprovalStepStatus.Pending));
            request.Steps.Add(NewStep(request, 2, ApprovalStepType.SeniorManager, manager.Id, ApprovalStepStatus.Waiting));
            request.Steps.Add(NewStep(request, 3, ApprovalStepType.AdministrativeRegistration, null, ApprovalStepStatus.Waiting));

            if (signature is not null) AddSignature(request, null, employee, "Solicitante", signature, actor, now);

            audit.Write(actor, resubmission ? "request.resubmitted" : "request.submitted", nameof(Request), request.Id.ToString(),
                new { request.Folio, request.Version, Supervisor = supervisor.Id, Manager = manager.Id });
            await notifications.OnTransitionAsync(request, WorkflowAction.Submit, actor, null, ct);
        }, ct);

        await notifications.FlushRealtimeAsync(ct);
        return Result(request, "Solicitud enviada a tu jefa directa.");
    }

    // ── Filtros 1 y 2: decisiones gerenciales ────────────────────────────────

    public async Task<WorkflowResultDto> DecideAsync(Actor actor, Guid id, DecisionInput input, CancellationToken ct = default)
    {
        var approver = await guard.RequireActiveAsync(actor, ct);
        var request = await LoadForCommandAsync(id, actor, ct);
        if (Duplicate(request, input.IdempotencyKey, actor) is { } dup) return dup;

        ApprovalStepType stepType;
        if (request.Status == RequestStatus.PendingSupervisor && request.AssignedSupervisorId == actor.EmployeeId) stepType = ApprovalStepType.DirectSupervisor;
        else if (request.Status == RequestStatus.PendingManager && request.AssignedManagerId == actor.EmployeeId) stepType = ApprovalStepType.SeniorManager;
        else if (request.AssignedSupervisorId == actor.EmployeeId || request.AssignedManagerId == actor.EmployeeId)
            throw new ConflictException($"La solicitud ya no está pendiente de su decisión (estado actual: {Labels.Status(request.Status)}).");
        else throw new ForbiddenException("Solo la persona asignada en el filtro vigente puede decidir esta solicitud.");

        if (request.EmployeeId == actor.EmployeeId) throw new ForbiddenException("Nadie puede autorizar sus propias solicitudes.");
        if (input.ExpectedVersion != request.Version)
            throw new ConflictException("La solicitud cambió desde que la abrió. Recargue el expediente y revise la versión vigente.");

        var comment = Text.Clean(input.Comment);
        var errors = RequestRules.Annotations(input);
        if (input.Decision is ApprovalDecisionType.Reject or ApprovalDecisionType.Return && (comment is null || comment.Length < 10))
            errors.Add("Para rechazar o devolver es obligatorio escribir la justificación (mínimo 10 caracteres).");
        byte[]? signature = null;
        if (input.Decision == ApprovalDecisionType.Approve)
        {
            if (string.IsNullOrWhiteSpace(input.SignaturePngBase64)) errors.Add("Para aprobar es necesario firmar.");
            if (!input.SignatureConsent) errors.Add("Debe confirmar expresamente que firma esta versión de la solicitud.");
        }
        if (errors.Count > 0) throw new BusinessRuleException(errors);
        if (!string.IsNullOrWhiteSpace(input.SignaturePngBase64)) signature = DecodeSignature(input.SignaturePngBase64);

        // Integridad: el contenido actual debe coincidir con el hash registrado de la versión.
        if (RequestContentHasher.Compute(request) != request.ContentHash)
        {
            logger.LogError("Hash de contenido no coincide para {Folio}", request.Folio);
            throw new ConflictException("La integridad del expediente no pudo verificarse. Contacte al administrador de Producto.");
        }

        var action = RequestStateMachine.DecisionAction(stepType, input.Decision);
        await AtomicAsync(async () =>
        {
            var now = clock.UtcNow;
            var step = request.Steps.Single(s => s.RequestVersion == request.Version && s.Type == stepType);
            var decision = Record(request, action, actor, comment, input.IdempotencyKey, step.Id == 0 ? null : step.Id);
            step.ActorEmployeeId = actor.EmployeeId;
            step.ActedAtUtc = now;
            step.Comment = comment;
            step.Status = input.Decision switch
            {
                ApprovalDecisionType.Approve => ApprovalStepStatus.Approved,
                ApprovalDecisionType.Reject => ApprovalStepStatus.Rejected,
                _ => ApprovalStepStatus.Returned
            };
            if (signature is not null)
                AddSignature(request, decision, approver, stepType == ApprovalStepType.DirectSupervisor ? "Jefa directa" : "Jefe superior", signature, actor, now);

            switch (input.Decision)
            {
                case ApprovalDecisionType.Approve when stepType == ApprovalStepType.DirectSupervisor:
                    Record(request, WorkflowAction.RouteToManager, Actor.System, null, null, null);
                    request.Steps.Single(s => s.RequestVersion == request.Version && s.Type == ApprovalStepType.SeniorManager).Status = ApprovalStepStatus.Pending;
                    break;
                case ApprovalDecisionType.Approve:
                    Record(request, WorkflowAction.RouteToAdministrative, Actor.System, null, null, null);
                    request.Steps.Single(s => s.RequestVersion == request.Version && s.Type == ApprovalStepType.AdministrativeRegistration).Status = ApprovalStepStatus.Pending;
                    request.Administrative ??= new AdministrativeRegistration { RequestId = request.Id };
                    if (request.Kind == RequestKind.Vacation) await ConsumeVacationAsync(request, actor, ct);
                    break;
                case ApprovalDecisionType.Reject:
                    foreach (var s in request.Steps.Where(s => s.RequestVersion == request.Version && s.Status is ApprovalStepStatus.Waiting or ApprovalStepStatus.Pending))
                        s.Status = ApprovalStepStatus.Cancelled;
                    break;
                case ApprovalDecisionType.Return:
                    request.LastReturnComment = comment;
                    foreach (var s in request.Steps.Where(s => s.RequestVersion == request.Version && s.Status is ApprovalStepStatus.Waiting or ApprovalStepStatus.Pending))
                        s.Status = ApprovalStepStatus.Cancelled;
                    break;
            }

            audit.Write(actor, $"request.{action.ToString().ToLowerInvariant()}", nameof(Request), request.Id.ToString(),
                new { request.Folio, request.Version, Decision = input.Decision.ToString(), Signed = signature is not null });
            await notifications.OnTransitionAsync(request, action, actor, comment, ct);
        }, ct);

        await notifications.FlushRealtimeAsync(ct);
        var message = input.Decision switch
        {
            ApprovalDecisionType.Approve when stepType == ApprovalStepType.DirectSupervisor => "Solicitud aprobada y turnada al jefe superior.",
            ApprovalDecisionType.Approve => "Solicitud autorizada definitivamente y remitida a registro administrativo.",
            ApprovalDecisionType.Reject => "Solicitud rechazada. Se notificó a las personas involucradas.",
            _ => "Solicitud devuelta al empleado para corrección."
        };
        return Result(request, message);
    }

    // ── Filtro 3: registro administrativo ────────────────────────────────────

    public async Task<WorkflowResultDto> AdministrativeAsync(Actor actor, Guid id, AdministrativeInput input, CancellationToken ct = default)
    {
        var registrar = await guard.RequireRoleAsync(actor, UserRole.AdministrativeRegistrar, ct);
        var request = await LoadForCommandAsync(id, actor, ct);
        if (Duplicate(request, input.IdempotencyKey, actor) is { } dup) return dup;
        if (!RequestAccess.IsAdministrativeStage(request.Status))
            throw new ConflictException("La solicitud aún no cuenta con las dos autorizaciones gerenciales.");
        var comment = Text.Clean(input.Comment);
        if (input.Action == AdministrativeAction.Observe && (comment is null || comment.Length < 10))
            throw new BusinessRuleException("Describa la observación administrativa (mínimo 10 caracteres).");

        string message;
        await AtomicAsync(async () =>
        {
            var now = clock.UtcNow;
            var reg = request.Administrative ??= new AdministrativeRegistration { RequestId = request.Id };
            if (input.Action == AdministrativeAction.Receive)
            {
                if (request.Status != RequestStatus.PendingAdministrativeRegistration && request.Status != RequestStatus.AdministrativeObserved)
                    throw new ConflictException("Solo se puede acusar recepción de solicitudes pendientes de registro.");
                if (reg.ReceivedAtUtc is not null) throw new ConflictException("La recepción ya había sido registrada.");
                reg.ReceivedAtUtc = now; reg.ReceivedByEmployeeId = registrar.Id; reg.ReceivedByName = registrar.FullName;
                db.ApprovalDecisions.Add(new ApprovalDecision
                {
                    Id = Guid.NewGuid(), RequestId = request.Id, ActorEmployeeId = actor.EmployeeId, ActorName = actor.Name,
                    Action = WorkflowAction.AdministrativeReceive, FromStatus = request.Status, ToStatus = request.Status,
                    Comment = comment, RequestVersion = request.Version, OccurredAtUtc = now, IdempotencyKey = input.IdempotencyKey
                });
                request.UpdatedAtUtc = now;
                audit.Write(actor, "request.administrative_receive", nameof(Request), request.Id.ToString(), new { request.Folio });
                return;
            }

            var action = RequestStateMachine.AdministrativeWorkflowAction(input.Action);
            if (!RequestStateMachine.CanApply(request.Status, action)) throw new InvalidTransitionException(request.Status, action);
            Record(request, action, actor, comment, input.IdempotencyKey, null);
            var step = request.Steps.FirstOrDefault(s => s.RequestVersion == request.Version && s.Type == ApprovalStepType.AdministrativeRegistration);
            switch (input.Action)
            {
                case AdministrativeAction.Observe:
                    reg.Observations = string.IsNullOrEmpty(reg.Observations)
                        ? $"[{clock.LocalNow:dd/MM/yyyy HH:mm}] {comment}"
                        : $"{reg.Observations}\n[{clock.LocalNow:dd/MM/yyyy HH:mm}] {comment}";
                    break;
                case AdministrativeAction.Register:
                    reg.ReceivedAtUtc ??= now; reg.ReceivedByEmployeeId ??= registrar.Id; reg.ReceivedByName ??= registrar.FullName;
                    reg.RegisteredAtUtc = now; reg.RegisteredByEmployeeId = registrar.Id; reg.RegisteredByName = registrar.FullName;
                    reg.ExternalReference = Text.Clean(input.ExternalReference) ?? reg.ExternalReference;
                    if (comment is not null) reg.Observations = string.IsNullOrEmpty(reg.Observations) ? comment : $"{reg.Observations}\n{comment}";
                    if (step is not null) { step.Status = ApprovalStepStatus.Registered; step.ActedAtUtc = now; step.ActorEmployeeId = registrar.Id; step.Comment = comment; }
                    break;
                case AdministrativeAction.Complete:
                    reg.ProcessedAtUtc = now; reg.ProcessedByEmployeeId = registrar.Id; reg.ProcessedByName = registrar.FullName;
                    break;
            }
            audit.Write(actor, $"request.administrative_{input.Action.ToString().ToLowerInvariant()}", nameof(Request), request.Id.ToString(), new { request.Folio });
            await notifications.OnTransitionAsync(request, action, actor, comment, ct);
        }, ct);
        message = Labels.AdministrativeAction(input.Action) + ".";
        await notifications.FlushRealtimeAsync(ct);
        return Result(request, message);
    }

    // ── Cancelación ──────────────────────────────────────────────────────────

    public async Task<WorkflowResultDto> CancelAsync(Actor actor, Guid id, CancelInput input, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var request = await LoadForCommandAsync(id, actor, ct);
        if (request.EmployeeId != actor.EmployeeId) throw new ForbiddenException("Solo el solicitante puede cancelar su solicitud.");
        if (request.Status == RequestStatus.Cancelled) return Result(request, "La solicitud ya estaba cancelada.", true);
        if (!RequestStateMachine.CanApply(request.Status, WorkflowAction.Cancel))
            throw new ConflictException($"No se puede cancelar una solicitud en estado «{Labels.Status(request.Status)}».");

        await AtomicAsync(async () =>
        {
            var reason = Text.Clean(input.Reason);
            Record(request, WorkflowAction.Cancel, actor, reason, null, null);
            foreach (var s in request.Steps.Where(s => s.RequestVersion == request.Version && s.Status is ApprovalStepStatus.Pending or ApprovalStepStatus.Waiting))
                s.Status = ApprovalStepStatus.Cancelled;
            audit.Write(actor, "request.cancelled", nameof(Request), request.Id.ToString(), new { request.Folio, reason });
            await notifications.OnTransitionAsync(request, WorkflowAction.Cancel, actor, reason, ct);
        }, ct);
        await notifications.FlushRealtimeAsync(ct);
        return Result(request, "Solicitud cancelada.");
    }

    // ── Adjuntos ─────────────────────────────────────────────────────────────

    public async Task<AttachmentDto> AddAttachmentAsync(Actor actor, Guid requestId, string fileName, string contentType, Stream content, long length, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var request = await LoadForCommandAsync(requestId, actor, ct);
        if (request.EmployeeId != actor.EmployeeId) throw new ForbiddenException("Solo el solicitante puede adjuntar documentos.");
        if (!request.IsEditable) throw new ConflictException("Solo se pueden adjuntar documentos en borrador o en corrección.");
        var opts = options.Value;
        var safeName = Path.GetFileName(fileName ?? "").Trim();
        var ext = Path.GetExtension(safeName).ToLowerInvariant();
        if (safeName.Length is 0 or > 150) throw new BusinessRuleException("Nombre de archivo inválido.");
        if (!AllowedExtensions.Contains(ext)) throw new BusinessRuleException("Tipo de archivo no permitido. Use PDF, PNG, JPG, DOCX o XLSX.");
        if (length <= 0 || length > opts.MaxAttachmentBytes) throw new BusinessRuleException($"El archivo debe pesar menos de {opts.MaxAttachmentBytes / (1024 * 1024)} MB.");
        if (request.Attachments.Count(a => !a.IsDeleted) >= opts.MaxAttachmentsPerRequest) throw new BusinessRuleException($"Máximo {opts.MaxAttachmentsPerRequest} archivos por solicitud.");

        // Verificación de firma de archivo (magic bytes) para evitar contenidos disfrazados.
        using var buffer = new MemoryStream();
        await content.CopyToAsync(buffer, ct);
        if (buffer.Length > opts.MaxAttachmentBytes) throw new BusinessRuleException("El archivo excede el tamaño permitido.");
        var bytes = buffer.ToArray();
        if (!FileSignatures.Matches(ext, bytes)) throw new BusinessRuleException("El contenido del archivo no corresponde a su extensión.");

        buffer.Position = 0;
        var stored = await storage.SaveAsync(buffer, ext, ct);
        var attachment = new Attachment
        {
            Id = Guid.NewGuid(), RequestId = request.Id, FileName = safeName, ContentType = FileSignatures.ContentType(ext),
            SizeBytes = stored.SizeBytes, Sha256 = stored.Sha256, StorageKey = stored.StorageKey,
            UploadedByEmployeeId = actor.EmployeeId, UploadedByName = actor.Name, UploadedAtUtc = clock.UtcNow
        };
        await AtomicAsync(() =>
        {
            var before = request.ContentHash;
            request.Attachments.Add(attachment);
            db.Attachments.Add(attachment);
            RefreshContentHash(request, before, actor, "Se modificaron los documentos adjuntos después de la firma.");
            audit.Write(actor, "attachment.uploaded", nameof(Attachment), attachment.Id.ToString(), new { request.Folio, attachment.FileName, attachment.Sha256 });
            return Task.CompletedTask;
        }, ct);
        return new AttachmentDto(attachment.Id, attachment.FileName, attachment.ContentType, attachment.SizeBytes, attachment.Sha256, attachment.UploadedByName, attachment.UploadedAtUtc);
    }

    public async Task RemoveAttachmentAsync(Actor actor, Guid requestId, Guid attachmentId, CancellationToken ct = default)
    {
        await guard.RequireActiveAsync(actor, ct);
        var request = await LoadForCommandAsync(requestId, actor, ct);
        if (request.EmployeeId != actor.EmployeeId || !request.IsEditable) throw new ForbiddenException("No se puede eliminar este archivo.");
        var attachment = request.Attachments.FirstOrDefault(a => a.Id == attachmentId && !a.IsDeleted) ?? throw new NotFoundException();
        await AtomicAsync(() =>
        {
            var before = request.ContentHash;
            attachment.IsDeleted = true;
            RefreshContentHash(request, before, actor, "Se modificaron los documentos adjuntos después de la firma.");
            audit.Write(actor, "attachment.removed", nameof(Attachment), attachment.Id.ToString(), new { request.Folio, attachment.FileName });
            return Task.CompletedTask;
        }, ct);
    }

    // ── Utilidades internas ──────────────────────────────────────────────────

    private async Task<Request> LoadForCommandAsync(Guid id, Actor actor, CancellationToken ct)
    {
        var request = await db.Requests.WithDetail().FirstOrDefaultAsync(r => r.Id == id, ct);
        if (request is null || !RequestAccess.CanView(request, actor)) throw new NotFoundException();
        return request;
    }

    private static RequestInput ToInput(Request r)
    {
        var p = r.PrimaryPeriod!;
        return new RequestInput
        {
            Kind = r.Kind, StartDate = p.StartDate, EndDate = p.EndDate, StartTime = p.StartTime, EndTime = p.EndTime,
            IsFullDay = r.IsFullDay, Reason = r.Reason, Justification = r.Justification, Observations = r.Observations,
            LeaveCategoryId = r.LeaveCategoryId, Project = r.Overtime?.Project, Activity = r.Overtime?.Activity
        };
    }

    private void Apply(Request request, RequestInput input, ComputedRequest c)
    {
        request.Reason = input.Reason.Trim();
        request.Justification = Text.Clean(input.Justification);
        request.Observations = Text.Clean(input.Observations);
        request.LeaveCategoryId = input.Kind is RequestKind.PaidLeave or RequestKind.UnpaidLeave ? input.LeaveCategoryId : null;
        request.IsFullDay = c.IsFullDay;
        request.TotalHours = c.Hours;
        request.TotalDays = c.Days;

        var period = request.Periods.FirstOrDefault();
        if (period is null) { period = new RequestPeriod { RequestId = request.Id }; request.Periods.Add(period); }
        period.StartDate = c.StartDate; period.EndDate = c.EndDate; period.StartTime = c.StartTime; period.EndTime = c.EndTime;

        if (input.Kind == RequestKind.Overtime && c.Overtime is not null)
        {
            request.Overtime ??= new OvertimeRecord { RequestId = request.Id, EmployeeId = request.EmployeeId };
            request.Overtime.WorkDate = c.StartDate;
            request.Overtime.StartLocal = c.Overtime.StartLocal;
            request.Overtime.EndLocal = c.Overtime.EndLocal;
            request.Overtime.Hours = c.Overtime.Hours;
            request.Overtime.CrossesMidnight = c.Overtime.CrossesMidnight;
            request.Overtime.Project = Text.Clean(input.Project);
            request.Overtime.Activity = Text.Clean(input.Activity);
            request.Overtime.PeriodYear = c.StartDate.Year;
            request.Overtime.PeriodMonth = c.StartDate.Month;
        }
    }

    /// <summary>Si el contenido sustantivo cambió y existían firmas vigentes, sube la versión y las invalida.</summary>
    private void RefreshContentHash(Request request, string previousHash, Actor actor, string reason)
    {
        var newHash = RequestContentHasher.Compute(request);
        if (newHash == previousHash) return;
        if (request.Signatures.Any(s => s.IsValid) || request.Steps.Any(s => s.RequestVersion == request.Version))
        {
            request.Version++;
            InvalidateSignatures(request, reason);
            audit.Write(actor, "request.signatures_invalidated", nameof(Request), request.Id.ToString(), new { request.Folio, request.Version, reason });
            newHash = RequestContentHasher.Compute(request);
        }
        request.ContentHash = newHash;
    }

    private void InvalidateSignatures(Request request, string reason)
    {
        foreach (var s in request.Signatures.Where(s => s.IsValid))
        {
            s.IsValid = false;
            s.InvalidatedAtUtc = clock.UtcNow;
            s.InvalidationReason = reason;
        }
    }

    private ApprovalDecision Record(Request request, WorkflowAction action, Actor actor, string? comment, string? idempotencyKey, int? stepId)
    {
        var from = request.Status;
        var to = request.Apply(action, clock.UtcNow);
        var decision = new ApprovalDecision
        {
            Id = Guid.NewGuid(), RequestId = request.Id, ApprovalStepId = stepId, ActorEmployeeId = actor.EmployeeId == 0 ? null : actor.EmployeeId,
            ActorName = actor.Name, Action = action, FromStatus = from, ToStatus = to, Comment = comment,
            RequestVersion = request.Version, OccurredAtUtc = clock.UtcNow, IdempotencyKey = idempotencyKey
        };
        request.Decisions.Add(decision);
        db.ApprovalDecisions.Add(decision);
        return decision;
    }

    private static ApprovalStep NewStep(Request r, int order, ApprovalStepType type, int? assignee, ApprovalStepStatus status) =>
        new() { RequestId = r.Id, StepOrder = order, Type = type, AssigneeEmployeeId = assignee, Status = status, RequestVersion = r.Version };

    private void AddSignature(Request request, ApprovalDecision? decision, Employee signer, string role, byte[] png, Actor actor, DateTime now)
    {
        var signature = new ElectronicSignature
        {
            Id = Guid.NewGuid(), RequestId = request.Id, ApprovalDecisionId = decision?.Id, SignerEmployeeId = signer.Id, SignerName = signer.FullName,
            SignerRole = role, SignedAtUtc = now, RequestVersion = request.Version, DocumentHash = request.ContentHash,
            ImagePng = png, IpAddress = actor.IpAddress, UserAgent = Text.Summarize(actor.UserAgent, 250), IsValid = true
        };
        signature.SignatureHash = SignatureHasher.Compute(png, signature.DocumentHash, signer.Id, request.Id, request.Version, now);
        request.Signatures.Add(signature);
        db.ElectronicSignatures.Add(signature);
        audit.Write(actor, "signature.created", nameof(ElectronicSignature), signature.Id.ToString(),
            new { request.Folio, request.Version, signature.DocumentHash, signature.SignatureHash, role });
    }

    /// <summary>Descuento transaccional único por solicitud y versión (índice único evita duplicados).</summary>
    private async Task ConsumeVacationAsync(Request request, Actor actor, CancellationToken ct)
    {
        var year = request.PrimaryPeriod!.StartDate.Year;
        var balance = await db.VacationBalances.Include(b => b.Transactions).FirstOrDefaultAsync(b => b.EmployeeId == request.EmployeeId && b.PeriodYear == year, ct);
        if (balance is null)
        {
            balance = new VacationBalance { EmployeeId = request.EmployeeId, PeriodYear = year, EntitledDays = 0 };
            db.VacationBalances.Add(balance);
        }
        var key = $"consume:{request.Id:N}";
        if (balance.Transactions.Any(t => t.DeduplicationKey == key) || await db.VacationTransactions.AnyAsync(t => t.DeduplicationKey == key, ct)) return;
        var available = balance.EntitledDays + balance.Transactions.Sum(t => t.Days);
        var policy = await settings.GetPolicyAsync(ct);
        if (available < request.TotalDays && !policy.VacationAllowNegativeBalance)
            throw new BusinessRuleException($"Saldo insuficiente para autorizar: {Labels.Days(available)} disponibles.");
        var tx = new VacationTransaction
        {
            Id = Guid.NewGuid(), Type = VacationTransactionType.Consumption, Days = -request.TotalDays, RequestId = request.Id,
            Description = $"Solicitud {request.Folio} autorizada", CreatedByEmployeeId = actor.EmployeeId, CreatedByName = actor.Name,
            CreatedAtUtc = clock.UtcNow, DeduplicationKey = key
        };
        balance.Transactions.Add(tx);
        db.VacationTransactions.Add(tx);
    }

    private async Task<string> NextFolioAsync(CancellationToken ct)
    {
        var year = clock.Today.Year;
        var seq = await db.FolioSequences.FirstOrDefaultAsync(s => s.Year == year, ct);
        if (seq is null) { seq = new FolioSequence { Year = year, LastValue = 0 }; db.FolioSequences.Add(seq); }
        seq.LastValue++;
        seq.ConcurrencyStamp = Guid.NewGuid();
        return FolioFormatter.Format(year, seq.LastValue);
    }

    private static WorkflowResultDto? Duplicate(Request request, string? key, Actor actor)
    {
        if (string.IsNullOrEmpty(key)) return null;
        var existing = request.Decisions.FirstOrDefault(d => d.IdempotencyKey == key);
        if (existing is null) return null;
        if (existing.ActorEmployeeId != actor.EmployeeId) throw new ConflictException("Clave de idempotencia ya utilizada.");
        return Result(request, "La operación ya se había registrado; no se aplicó de nuevo.", true);
    }

    private static WorkflowResultDto Result(Request r, string message, bool duplicate = false) =>
        new(r.Id, r.Folio, r.Status, Labels.Status(r.Status), message, duplicate);

    internal static byte[] DecodeSignature(string base64)
    {
        var data = base64.Trim();
        var comma = data.IndexOf(',');
        if (data.StartsWith("data:", StringComparison.OrdinalIgnoreCase) && comma > 0) data = data[(comma + 1)..];
        byte[] bytes;
        try { bytes = Convert.FromBase64String(data); }
        catch (FormatException) { throw new BusinessRuleException("La firma no tiene un formato válido."); }
        if (bytes.Length < 200) throw new BusinessRuleException("La firma está vacía. Dibuje su firma en el recuadro.");
        if (bytes.Length > MaxSignatureBytes) throw new BusinessRuleException("La imagen de la firma es demasiado grande.");
        if (!FileSignatures.Matches(".png", bytes)) throw new BusinessRuleException("La firma debe ser una imagen PNG.");
        return bytes;
    }

    /// <summary>
    /// Ejecuta la unidad de trabajo dentro de una transacción. Los conflictos de concurrencia (dos aprobaciones
    /// simultáneas, doble clic) se traducen en <see cref="ConflictException"/> y nada se persiste.
    /// </summary>
    private async Task AtomicAsync(Func<Task> work, CancellationToken ct)
    {
        await using var tx = await db.Database.BeginTransactionAsync(ct);
        try
        {
            await work();
            await db.SaveChangesAsync(ct);
            await tx.CommitAsync(ct);
        }
        catch (DbUpdateConcurrencyException ex)
        {
            await tx.RollbackAsync(CancellationToken.None);
            notifications.DiscardRealtime();
            logger.LogWarning(ex, "Conflicto de concurrencia");
            throw new ConflictException("Otra persona u otra pestaña modificó la solicitud al mismo tiempo. Recargue el expediente.");
        }
        catch (DbUpdateException ex)
        {
            await tx.RollbackAsync(CancellationToken.None);
            notifications.DiscardRealtime();
            logger.LogWarning(ex, "Violación de unicidad o integridad");
            throw new ConflictException("La operación entró en conflicto con otra operación simultánea. Recargue e intente de nuevo.");
        }
        catch
        {
            notifications.DiscardRealtime();
            throw;
        }
    }
}

/// <summary>Validación de contenido por "magic bytes".</summary>
public static class FileSignatures
{
    public static bool Matches(string ext, byte[] b) => ext switch
    {
        ".pdf" => b.Length > 4 && b[0] == 0x25 && b[1] == 0x50 && b[2] == 0x44 && b[3] == 0x46,
        ".png" => b.Length > 8 && b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47,
        ".jpg" or ".jpeg" => b.Length > 3 && b[0] == 0xFF && b[1] == 0xD8 && b[2] == 0xFF,
        ".docx" or ".xlsx" => b.Length > 4 && b[0] == 0x50 && b[1] == 0x4B && b[2] == 0x03 && b[3] == 0x04,
        _ => false
    };

    public static string ContentType(string ext) => ext switch
    {
        ".pdf" => "application/pdf",
        ".png" => "image/png",
        ".jpg" or ".jpeg" => "image/jpeg",
        ".docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _ => "application/octet-stream"
    };
}
