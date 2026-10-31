using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.Domain;

/// <summary>Campos comunes de auditoría técnica y concurrencia optimista.</summary>
public abstract class TrackedEntity
{
    public DateTime CreatedAtUtc { get; set; }
    public DateTime UpdatedAtUtc { get; set; }
    /// <summary>Token de concurrencia portable (SQLite y SQL Server). Se renueva en cada guardado.</summary>
    public Guid ConcurrencyStamp { get; set; } = Guid.NewGuid();
}

public class Department : TrackedEntity
{
    public int Id { get; set; }
    public string Code { get; set; } = "";
    public string Name { get; set; } = "";
    public bool IsActive { get; set; } = true;
}

public class Position : TrackedEntity
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public bool IsActive { get; set; } = true;
}

public class Employee : TrackedEntity
{
    public int Id { get; set; }
    public string EmployeeNumber { get; set; } = "";
    public string FullName { get; set; } = "";
    public string Email { get; set; } = "";
    /// <summary>Correo normalizado (minúsculas) con índice único.</summary>
    public string NormalizedEmail { get; set; } = "";
    public int DepartmentId { get; set; }
    public Department? Department { get; set; }
    public string? Area { get; set; }
    public int? PositionId { get; set; }
    public Position? Position { get; set; }
    public DateOnly? HireDate { get; set; }
    public bool IsActive { get; set; } = true;
    public bool IsSynthetic { get; set; }

    public UserAccount? User { get; set; }

    public string FirstName => FullName.Split(' ', StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? FullName;
}

/// <summary>Cuenta de acceso. En producción se vincula a Microsoft Entra ID mediante ExternalObjectId.</summary>
public class UserAccount : TrackedEntity
{
    public int Id { get; set; }
    public int EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public UserRole Roles { get; set; } = UserRole.Employee;
    /// <summary>Hash PBKDF2 (ASP.NET Core Identity v3). Solo para modo DEMO/TEST; nulo en producción con Entra ID.</summary>
    public string? PasswordHash { get; set; }
    public string? ExternalObjectId { get; set; }
    public bool IsActive { get; set; } = true;
    public int FailedLoginCount { get; set; }
    public DateTime? LockoutEndUtc { get; set; }
    public DateTime? LastLoginUtc { get; set; }
    /// <summary>Cambia al modificar roles o desactivar; invalida sesiones abiertas.</summary>
    public Guid SecurityStamp { get; set; } = Guid.NewGuid();
}

/// <summary>Jerarquía de autorización vigente e histórica de cada empleado.</summary>
public class ReportingHierarchy : TrackedEntity
{
    public int Id { get; set; }
    public int EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public int? DirectSupervisorId { get; set; }
    public Employee? DirectSupervisor { get; set; }
    public int? SeniorManagerId { get; set; }
    public Employee? SeniorManager { get; set; }
    public DateOnly EffectiveFrom { get; set; }
    public DateOnly? EffectiveTo { get; set; }
    public bool IsCurrent { get; set; } = true;
}

/// <summary>Catálogo de tipos de solicitud.</summary>
public class RequestType : TrackedEntity
{
    public int Id { get; set; }
    public RequestKind Kind { get; set; }
    public string Name { get; set; } = "";
    public string Description { get; set; } = "";
    public bool RequiresSignatureToApprove { get; set; } = true;
    public bool IsActive { get; set; } = true;
}

/// <summary>Clasificación configurable de permisos (con o sin goce).</summary>
public class LeaveCategory : TrackedEntity
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public RequestKind AppliesTo { get; set; }
    public bool RequiresAttachment { get; set; }
    public bool IsActive { get; set; } = true;
}

public class Holiday : TrackedEntity
{
    public int Id { get; set; }
    public DateOnly Date { get; set; }
    public string Name { get; set; } = "";
    public bool IsActive { get; set; } = true;
}

public class Request : TrackedEntity
{
    public Guid Id { get; set; }
    public string Folio { get; set; } = "";
    public int EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public int RequestTypeId { get; set; }
    public RequestType? RequestType { get; set; }
    public RequestKind Kind { get; set; }
    public RequestStatus Status { get; set; } = RequestStatus.Draft;

    public string Reason { get; set; } = "";
    public string? Justification { get; set; }
    public string? Observations { get; set; }
    public int? LeaveCategoryId { get; set; }
    public LeaveCategory? LeaveCategory { get; set; }
    public bool IsFullDay { get; set; }

    public decimal TotalHours { get; set; }
    public decimal TotalDays { get; set; }

    /// <summary>Versión sustantiva. Aumenta cada vez que cambia información relevante; invalida firmas previas.</summary>
    public int Version { get; set; } = 1;
    /// <summary>SHA-256 del contenido canónico de la versión actual.</summary>
    public string ContentHash { get; set; } = "";

    /// <summary>Instantánea de la jerarquía al momento del envío (no cambia aunque el organigrama cambie).</summary>
    public int? AssignedSupervisorId { get; set; }
    public Employee? AssignedSupervisor { get; set; }
    public int? AssignedManagerId { get; set; }
    public Employee? AssignedManager { get; set; }

    public DateTime? SubmittedAtUtc { get; set; }
    public DateTime? StatusChangedAtUtc { get; set; }
    public DateTime? ClosedAtUtc { get; set; }
    public string? LastReturnComment { get; set; }

    public List<RequestPeriod> Periods { get; set; } = [];
    public OvertimeRecord? Overtime { get; set; }
    public List<ApprovalStep> Steps { get; set; } = [];
    public List<ApprovalDecision> Decisions { get; set; } = [];
    public List<ElectronicSignature> Signatures { get; set; } = [];
    public List<Attachment> Attachments { get; set; } = [];
    public AdministrativeRegistration? Administrative { get; set; }

    public RequestPeriod? PrimaryPeriod => Periods.OrderBy(p => p.StartDate).FirstOrDefault();

    public bool IsEditable => Status is RequestStatus.Draft or RequestStatus.ReturnedForCorrection;
    public bool IsOpen => Status is RequestStatus.Submitted or RequestStatus.PendingSupervisor or RequestStatus.SupervisorApproved
        or RequestStatus.PendingManager or RequestStatus.ManagerApproved;
    public bool IsFinalApproved => Status is RequestStatus.ManagerApproved or RequestStatus.PendingAdministrativeRegistration
        or RequestStatus.AdministrativeObserved or RequestStatus.AdministrativeRegistered or RequestStatus.Completed;
    public bool IsRejected => Status is RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected;
    /// <summary>Solicitudes que ocupan el calendario (para detectar traslapes).</summary>
    public bool BlocksCalendar => Status is not (RequestStatus.Draft or RequestStatus.Cancelled
        or RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected);

    /// <summary>
    /// Aplica una transición validada por la máquina de estados.
    /// Lanza <see cref="InvalidTransitionException"/> si no es válida desde el estado actual.
    /// </summary>
    public RequestStatus Apply(WorkflowAction action, DateTime nowUtc)
    {
        var target = RequestStateMachine.GetTarget(Status, action);
        Status = target;
        StatusChangedAtUtc = nowUtc;
        if (RequestStateMachine.IsTerminal(target)) ClosedAtUtc = nowUtc;
        return target;
    }
}

/// <summary>Periodo de la solicitud. Tiempo extra: una fecha con horas (puede cruzar medianoche). Vacaciones: rango de fechas.</summary>
public class RequestPeriod
{
    public int Id { get; set; }
    public Guid RequestId { get; set; }
    public DateOnly StartDate { get; set; }
    public DateOnly EndDate { get; set; }
    public TimeOnly? StartTime { get; set; }
    public TimeOnly? EndTime { get; set; }
}

public class OvertimeRecord
{
    public Guid RequestId { get; set; }
    public int EmployeeId { get; set; }
    public DateOnly WorkDate { get; set; }
    /// <summary>Inicio y fin en hora local (America/Mexico_City por defecto).</summary>
    public DateTime StartLocal { get; set; }
    public DateTime EndLocal { get; set; }
    public decimal Hours { get; set; }
    public bool CrossesMidnight { get; set; }
    public string? Project { get; set; }
    public string? Activity { get; set; }
    public int PeriodYear { get; set; }
    public int PeriodMonth { get; set; }
}

public class ApprovalStep
{
    public int Id { get; set; }
    public Guid RequestId { get; set; }
    public int StepOrder { get; set; }
    public ApprovalStepType Type { get; set; }
    public int? AssigneeEmployeeId { get; set; }
    public Employee? Assignee { get; set; }
    public ApprovalStepStatus Status { get; set; }
    public int? ActorEmployeeId { get; set; }
    public DateTime? ActedAtUtc { get; set; }
    public string? Comment { get; set; }
    public int RequestVersion { get; set; }
}

/// <summary>Bitácora inmutable de cada transición del flujo (nunca se actualiza ni se borra).</summary>
public class ApprovalDecision
{
    public Guid Id { get; set; }
    public Guid RequestId { get; set; }
    public int? ApprovalStepId { get; set; }
    public int? ActorEmployeeId { get; set; }
    public string ActorName { get; set; } = "";
    public WorkflowAction Action { get; set; }
    public RequestStatus FromStatus { get; set; }
    public RequestStatus ToStatus { get; set; }
    public string? Comment { get; set; }
    public int RequestVersion { get; set; }
    public DateTime OccurredAtUtc { get; set; }
    /// <summary>Clave de idempotencia enviada por el cliente. Única por solicitud.</summary>
    public string? IdempotencyKey { get; set; }
}

public class ElectronicSignature
{
    public Guid Id { get; set; }
    public Guid RequestId { get; set; }
    public Guid? ApprovalDecisionId { get; set; }
    public int SignerEmployeeId { get; set; }
    public string SignerName { get; set; } = "";
    public string SignerRole { get; set; } = "";
    public DateTime SignedAtUtc { get; set; }
    public int RequestVersion { get; set; }
    /// <summary>Hash del contenido de la solicitud firmado (versión exacta).</summary>
    public string DocumentHash { get; set; } = "";
    /// <summary>SHA-256 de (imagen + hash de documento + firmante + fecha + solicitud).</summary>
    public string SignatureHash { get; set; } = "";
    public byte[] ImagePng { get; set; } = [];
    public string? IpAddress { get; set; }
    public string? UserAgent { get; set; }
    public bool IsValid { get; set; } = true;
    public DateTime? InvalidatedAtUtc { get; set; }
    public string? InvalidationReason { get; set; }
    public const string SimpleElectronicSignature = "Firma electrónica simple (trazo autenticado)";
}

public class Attachment
{
    public Guid Id { get; set; }
    public Guid RequestId { get; set; }
    public string FileName { get; set; } = "";
    public string ContentType { get; set; } = "";
    public long SizeBytes { get; set; }
    public string Sha256 { get; set; } = "";
    public string StorageKey { get; set; } = "";
    public int UploadedByEmployeeId { get; set; }
    public string UploadedByName { get; set; } = "";
    public DateTime UploadedAtUtc { get; set; }
    public bool IsDeleted { get; set; }
}

public class VacationBalance : TrackedEntity
{
    public int Id { get; set; }
    public int EmployeeId { get; set; }
    public Employee? Employee { get; set; }
    public int PeriodYear { get; set; }
    public decimal EntitledDays { get; set; }
    public List<VacationTransaction> Transactions { get; set; } = [];
}

public class VacationTransaction
{
    public Guid Id { get; set; }
    public int VacationBalanceId { get; set; }
    public Guid? RequestId { get; set; }
    public VacationTransactionType Type { get; set; }
    /// <summary>Positivo suma saldo, negativo descuenta.</summary>
    public decimal Days { get; set; }
    public string Description { get; set; } = "";
    public int? CreatedByEmployeeId { get; set; }
    public string CreatedByName { get; set; } = "";
    public DateTime CreatedAtUtc { get; set; }
    /// <summary>Evita descuentos duplicados: único por (RequestId, Type, RequestVersion).</summary>
    public string? DeduplicationKey { get; set; }
}

public class Notification
{
    public Guid Id { get; set; }
    public int RecipientEmployeeId { get; set; }
    public NotificationType Type { get; set; }
    public string Title { get; set; } = "";
    public string Message { get; set; } = "";
    public Guid? RequestId { get; set; }
    public string? Link { get; set; }
    public DateTime CreatedAtUtc { get; set; }
    public DateTime? ReadAtUtc { get; set; }
    public string? DeduplicationKey { get; set; }
}

public class EmailOutboxMessage
{
    public Guid Id { get; set; }
    public string DeduplicationKey { get; set; } = "";
    public string ToAddresses { get; set; } = "";
    public string? CcAddresses { get; set; }
    public string Subject { get; set; } = "";
    public string HtmlBody { get; set; } = "";
    public string EventType { get; set; } = "";
    public Guid? RequestId { get; set; }
    public string? Folio { get; set; }
    public EmailStatus Status { get; set; } = EmailStatus.Pending;
    public int Attempts { get; set; }
    public DateTime NextAttemptAtUtc { get; set; }
    public DateTime CreatedAtUtc { get; set; }
    public DateTime? SentAtUtc { get; set; }
    public string? LastError { get; set; }
    public string Provider { get; set; } = "";
    public string? ProviderMessageId { get; set; }
    public Guid ConcurrencyStamp { get; set; } = Guid.NewGuid();
}

/// <summary>Bitácora de auditoría encadenada por hash (detección de alteraciones).</summary>
public class AuditLog
{
    public long Id { get; set; }
    /// <summary>Posición en la cadena de hash (única y consecutiva). Se asigna al guardar.</summary>
    public long Sequence { get; set; }
    public DateTime OccurredAtUtc { get; set; }
    public int? ActorEmployeeId { get; set; }
    public string ActorName { get; set; } = "";
    public string Action { get; set; } = "";
    public string EntityType { get; set; } = "";
    public string EntityId { get; set; } = "";
    public string? Details { get; set; }
    public string? IpAddress { get; set; }
    public string PreviousHash { get; set; } = "";
    public string Hash { get; set; } = "";
}

public class AdministrativeRegistration : TrackedEntity
{
    public int Id { get; set; }
    public Guid RequestId { get; set; }
    public int? ReceivedByEmployeeId { get; set; }
    public string? ReceivedByName { get; set; }
    public DateTime? ReceivedAtUtc { get; set; }
    public int? RegisteredByEmployeeId { get; set; }
    public string? RegisteredByName { get; set; }
    public DateTime? RegisteredAtUtc { get; set; }
    public int? ProcessedByEmployeeId { get; set; }
    public string? ProcessedByName { get; set; }
    public DateTime? ProcessedAtUtc { get; set; }
    public string? Observations { get; set; }
    public string? ExternalReference { get; set; }
}

public class ExcelExport
{
    public Guid Id { get; set; }
    public int ExportedByEmployeeId { get; set; }
    public string ExportedByName { get; set; } = "";
    public DateTime ExportedAtUtc { get; set; }
    public string FileName { get; set; } = "";
    public string Filters { get; set; } = "";
    public int RowCount { get; set; }
    public string Sha256 { get; set; } = "";
}

public class SystemSetting
{
    public string Key { get; set; } = "";
    public string Value { get; set; } = "";
    public string? Description { get; set; }
    public DateTime UpdatedAtUtc { get; set; }
    public string? UpdatedByName { get; set; }
}

/// <summary>Secuencia de folios por año (TF-AAAA-000000).</summary>
public class FolioSequence
{
    public int Year { get; set; }
    public int LastValue { get; set; }
    public Guid ConcurrencyStamp { get; set; } = Guid.NewGuid();
}
