using System.ComponentModel.DataAnnotations;

namespace GPV.ProductTimeFlow.Shared;

// ──────────────────────────────────────────────────────────────────────────────
// Contratos (DTOs) compartidos entre API, Web y Mobile.
// ──────────────────────────────────────────────────────────────────────────────

public sealed record PagedResult<T>(IReadOnlyList<T> Items, int Page, int PageSize, int TotalCount)
{
    public int TotalPages => PageSize <= 0 ? 0 : (int)Math.Ceiling(TotalCount / (double)PageSize);
}

/// <summary>Datos capturables de una solicitud (borrador o corrección).</summary>
public sealed class RequestInput
{
    [Required] public RequestKind Kind { get; set; } = RequestKind.Overtime;
    [Required] public DateOnly StartDate { get; set; }
    /// <summary>Fecha final (vacaciones y permisos de día completo). Para tiempo extra se ignora.</summary>
    public DateOnly? EndDate { get; set; }
    public TimeOnly? StartTime { get; set; }
    public TimeOnly? EndTime { get; set; }
    public bool IsFullDay { get; set; } = true;
    [Required, StringLength(500, MinimumLength = 5)] public string Reason { get; set; } = "";
    [StringLength(150)] public string? Project { get; set; }
    [StringLength(1000)] public string? Activity { get; set; }
    [StringLength(1000)] public string? Justification { get; set; }
    [StringLength(1000)] public string? Observations { get; set; }
    public int? LeaveCategoryId { get; set; }
}

public sealed class SubmitInput
{
    /// <summary>Firma opcional del empleado (PNG en base64, sin prefijo data:).</summary>
    public string? SignaturePngBase64 { get; set; }
    [Required, StringLength(80, MinimumLength = 8)] public string IdempotencyKey { get; set; } = Guid.NewGuid().ToString("N");
}

public sealed class DecisionInput
{
    [Required] public ApprovalDecisionType Decision { get; set; }
    [StringLength(1000)] public string? Comment { get; set; }
    /// <summary>Firma dibujada (PNG base64). Obligatoria para aprobar.</summary>
    public string? SignaturePngBase64 { get; set; }
    /// <summary>Confirmación explícita del firmante (casilla "Confirmo que firmo…").</summary>
    public bool SignatureConsent { get; set; }
    /// <summary>Versión sustantiva que el aprobador revisó. Si cambió, la decisión se rechaza.</summary>
    public int ExpectedVersion { get; set; }
    [Required, StringLength(80, MinimumLength = 8)] public string IdempotencyKey { get; set; } = Guid.NewGuid().ToString("N");
}

public sealed class AdministrativeInput
{
    [Required] public AdministrativeAction Action { get; set; }
    [StringLength(1000)] public string? Comment { get; set; }
    [StringLength(100)] public string? ExternalReference { get; set; }
    [Required, StringLength(80, MinimumLength = 8)] public string IdempotencyKey { get; set; } = Guid.NewGuid().ToString("N");
}

public sealed class CancelInput
{
    [StringLength(500)] public string? Reason { get; set; }
}

public sealed class RequestQuery
{
    public RequestScope Scope { get; set; } = RequestScope.Mine;
    public RequestStatus? Status { get; set; }
    public RequestKind? Kind { get; set; }
    public DateOnly? From { get; set; }
    public DateOnly? To { get; set; }
    public int? EmployeeId { get; set; }
    public string? Search { get; set; }
    /// <summary>"open" = en curso, "approved", "rejected", "closed".</summary>
    public string? Bucket { get; set; }
    public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 20;
}

public sealed record RequestSummaryDto
{
    public Guid Id { get; init; }
    public string Folio { get; init; } = "";
    public RequestKind Kind { get; init; }
    public string KindLabel => Labels.Kind(Kind);
    public RequestStatus Status { get; init; }
    public string StatusLabel => Labels.Status(Status);
    public string StatusTone => Labels.StatusTone(Status);
    public int EmployeeId { get; init; }
    public string EmployeeName { get; init; } = "";
    public string EmployeeNumber { get; init; } = "";
    public string? Area { get; init; }
    public DateOnly StartDate { get; init; }
    public DateOnly EndDate { get; init; }
    public TimeOnly? StartTime { get; init; }
    public TimeOnly? EndTime { get; init; }
    public bool IsFullDay { get; init; }
    public decimal Hours { get; init; }
    public decimal Days { get; init; }
    public string Reason { get; init; } = "";
    public DateTime CreatedAtUtc { get; init; }
    public DateTime? SubmittedAtUtc { get; init; }
    public DateTime UpdatedAtUtc { get; init; }
    public string? CurrentApproverName { get; init; }
    public int Version { get; init; }
    public bool IsUrgent { get; init; }
}

public sealed record ApprovalStepDto(
    int Order,
    ApprovalStepType Type,
    string TypeLabel,
    ApprovalStepStatus Status,
    string StatusLabel,
    string? AssigneeName,
    string? ActorName,
    DateTime? ActedAtUtc,
    string? Comment,
    int RequestVersion);

public sealed record HistoryEntryDto(
    DateTime OccurredAtUtc,
    string ActionLabel,
    string ActorName,
    string? FromStatusLabel,
    string? ToStatusLabel,
    string? Comment,
    int RequestVersion);

public sealed record SignatureDto(
    Guid Id,
    string SignerName,
    string SignerRole,
    DateTime SignedAtUtc,
    int RequestVersion,
    string DocumentHash,
    string SignatureHash,
    bool IsValid,
    string? InvalidationReason,
    string SignatureType,
    string? ImageDataUrl);

public sealed record AttachmentDto(Guid Id, string FileName, string ContentType, long SizeBytes, string Sha256, string UploadedByName, DateTime UploadedAtUtc);

public sealed record AdministrativeDto(
    string? ReceivedByName,
    DateTime? ReceivedAtUtc,
    string? RegisteredByName,
    DateTime? RegisteredAtUtc,
    string? ProcessedByName,
    DateTime? ProcessedAtUtc,
    string? Observations,
    string? ExternalReference);

public sealed record RequestPermissionsDto
{
    public bool CanEdit { get; init; }
    public bool CanSubmit { get; init; }
    public bool CanCancel { get; init; }
    public bool CanDecide { get; init; }
    public ApprovalStepType? DecisionStep { get; init; }
    public bool CanAdminReceive { get; init; }
    public bool CanAdminObserve { get; init; }
    public bool CanAdminRegister { get; init; }
    public bool CanAdminComplete { get; init; }
    public bool CanUploadAttachments { get; init; }
}

public sealed record RequestDetailDto
{
    public required RequestSummaryDto Summary { get; init; }
    public string? EmployeeEmail { get; init; }
    public string? Department { get; init; }
    public string? Position { get; init; }
    public string? Project { get; init; }
    public string? Activity { get; init; }
    public string? Justification { get; init; }
    public string? Observations { get; init; }
    public int? LeaveCategoryId { get; init; }
    public string? LeaveCategoryName { get; init; }
    public bool CrossesMidnight { get; init; }
    public string? SupervisorName { get; init; }
    public string? ManagerName { get; init; }
    public string ContentHash { get; init; } = "";
    public string? ReturnComment { get; init; }
    public IReadOnlyList<ApprovalStepDto> Steps { get; init; } = [];
    public IReadOnlyList<HistoryEntryDto> History { get; init; } = [];
    public IReadOnlyList<SignatureDto> Signatures { get; init; } = [];
    public IReadOnlyList<AttachmentDto> Attachments { get; init; } = [];
    public AdministrativeDto? Administrative { get; init; }
    public RequestPermissionsDto Permissions { get; init; } = new();
}

public sealed record WorkflowResultDto(Guid RequestId, string Folio, RequestStatus Status, string StatusLabel, string Message, bool WasDuplicate);

// ── Previews / cálculos ───────────────────────────────────────────────────────

public sealed class OvertimePreviewRequest
{
    public DateOnly Date { get; set; }
    public TimeOnly Start { get; set; }
    public TimeOnly End { get; set; }
    public Guid? ExcludeRequestId { get; set; }
}

public sealed record OvertimePreviewDto(
    decimal Hours,
    bool CrossesMidnight,
    DateTime StartLocal,
    DateTime EndLocal,
    IReadOnlyList<string> Errors,
    IReadOnlyList<string> Warnings);

public sealed class VacationPreviewRequest
{
    public DateOnly StartDate { get; set; }
    public DateOnly EndDate { get; set; }
    public Guid? ExcludeRequestId { get; set; }
}

public sealed record VacationPreviewDto(
    decimal BusinessDays,
    int CalendarDays,
    IReadOnlyList<string> HolidaysInRange,
    decimal AvailableBefore,
    decimal AvailableAfter,
    int TeammatesAbsentCount,
    IReadOnlyList<string> TeammatesAbsentNames,
    IReadOnlyList<string> Errors,
    IReadOnlyList<string> Warnings);

public sealed record VacationTransactionDto(DateTime CreatedAtUtc, string TypeLabel, decimal Days, string? Folio, string Description, string CreatedByName);

public sealed record VacationBalanceDto
{
    public int EmployeeId { get; init; }
    public string EmployeeName { get; init; } = "";
    public int PeriodYear { get; init; }
    public decimal Entitled { get; init; }
    public decimal Adjustments { get; init; }
    public decimal Used { get; init; }
    public decimal ApprovedUpcoming { get; init; }
    public decimal Pending { get; init; }
    public decimal Available { get; init; }
    public int PendingRequests { get; init; }
    public int RejectedRequests { get; init; }
    public IReadOnlyList<VacationTransactionDto> Transactions { get; init; } = [];
    public IReadOnlyList<RequestSummaryDto> Requests { get; init; } = [];
}

public sealed record OvertimeMonthlySummaryDto(
    int Year,
    int Month,
    decimal RequestedHours,
    decimal ApprovedHours,
    decimal RejectedHours,
    decimal PendingHours,
    IReadOnlyList<RequestSummaryDto> Items);

// ── Dashboard ─────────────────────────────────────────────────────────────────

public sealed record ChartPointDto(string Label, decimal Value, string? Tone = null);

public sealed record DashboardDto
{
    public required UserProfileDto Profile { get; init; }
    public int MyDrafts { get; init; }
    public int MyInProgress { get; init; }
    public int MyApproved { get; init; }
    public int MyRejected { get; init; }
    public int MyReturned { get; init; }
    public decimal VacationAvailable { get; init; }
    public decimal VacationPending { get; init; }
    public decimal OvertimeMonthHours { get; init; }
    public decimal OvertimeMonthApprovedHours { get; init; }
    public IReadOnlyList<RequestSummaryDto> MyRecent { get; init; } = [];
    public int UnreadNotifications { get; init; }

    // Aprobadores
    public int ApprovalsPending { get; init; }
    public int ApprovalsUrgent { get; init; }
    public int TeamSize { get; init; }
    public int DecisionsThisMonth { get; init; }
    public decimal TeamOvertimeMonthHours { get; init; }
    public IReadOnlyList<RequestSummaryDto> ApprovalQueue { get; init; } = [];
    public IReadOnlyList<ChartPointDto> TeamRequestsByKind { get; init; } = [];
    public IReadOnlyList<ChartPointDto> DepartmentStatus { get; init; } = [];
    public IReadOnlyList<ChartPointDto> OvertimeTrend { get; init; } = [];
    public IReadOnlyList<CalendarEventDto> UpcomingTeamAbsences { get; init; } = [];

    // Administración
    public int AdminPendingRegistration { get; init; }
    public int AdminObserved { get; init; }
    public int AdminRegistered { get; init; }
    public int ActiveEmployees { get; init; }
    public int EmailsPending { get; init; }
    public int EmailsFailed { get; init; }
}

public sealed record CalendarEventDto(
    Guid? RequestId,
    string Title,
    DateOnly Start,
    DateOnly End,
    RequestKind? Kind,
    RequestStatus? Status,
    bool IsMine,
    bool IsHoliday,
    string Tone);

// ── Notificaciones ────────────────────────────────────────────────────────────

public sealed record NotificationDto(Guid Id, NotificationType Type, string Title, string Message, Guid? RequestId, string? Link, DateTime CreatedAtUtc, bool IsRead);

// ── Identidad / empleados ────────────────────────────────────────────────────

public sealed record UserProfileDto
{
    public int EmployeeId { get; init; }
    public string EmployeeNumber { get; init; } = "";
    public string FullName { get; init; } = "";
    public string FirstName { get; init; } = "";
    public string Email { get; init; } = "";
    public UserRole Roles { get; init; }
    public IReadOnlyList<string> RoleLabels { get; init; } = [];
    public string? Department { get; init; }
    public string? Area { get; init; }
    public string? Position { get; init; }
    public string? SupervisorName { get; init; }
    public string? ManagerName { get; init; }
    public string EnvironmentMode { get; init; } = "Demo";
}

public sealed class LoginRequest
{
    [Required, EmailAddress, StringLength(200)] public string Email { get; set; } = "";
    [Required, StringLength(200)] public string Password { get; set; } = "";
}

public sealed record LoginResponse(string AccessToken, DateTime ExpiresAtUtc, UserProfileDto Profile);

public sealed record EmployeeDto
{
    public int Id { get; init; }
    public string EmployeeNumber { get; init; } = "";
    public string FullName { get; init; } = "";
    public string Email { get; init; } = "";
    public int DepartmentId { get; init; }
    public string Department { get; init; } = "";
    public string? Area { get; init; }
    public int? PositionId { get; init; }
    public string? Position { get; init; }
    public int? SupervisorId { get; init; }
    public string? SupervisorName { get; init; }
    public int? ManagerId { get; init; }
    public string? ManagerName { get; init; }
    public bool IsActive { get; init; }
    public DateOnly? HireDate { get; init; }
    public UserRole Roles { get; init; }
    public decimal VacationAvailable { get; init; }
    public bool HasLocalLogin { get; init; }
    public bool IsLockedOut { get; init; }
}

public sealed class EmployeeInput
{
    [Required, StringLength(20, MinimumLength = 1), RegularExpression("^[A-Za-z0-9-]+$", ErrorMessage = "Solo letras, números y guiones.")]
    public string EmployeeNumber { get; set; } = "";
    [Required, StringLength(150, MinimumLength = 3)] public string FullName { get; set; } = "";
    [Required, EmailAddress, StringLength(200)] public string Email { get; set; } = "";
    [Range(1, int.MaxValue, ErrorMessage = "Seleccione un departamento.")] public int DepartmentId { get; set; }
    [StringLength(100)] public string? Area { get; set; }
    public int? PositionId { get; set; }
    public int? SupervisorId { get; set; }
    public int? ManagerId { get; set; }
    public DateOnly? HireDate { get; set; }
    public UserRole Roles { get; set; } = UserRole.Employee;
    public bool IsActive { get; set; } = true;
    [Range(0, 60)] public decimal? InitialVacationDays { get; set; }
}

public sealed record ImportRowResultDto(int RowNumber, string? EmployeeNumber, bool Success, string Message);
public sealed record ImportResultDto(int Created, int Updated, int Failed, IReadOnlyList<ImportRowResultDto> Rows, bool DryRun);

public sealed record OrgNodeDto(int EmployeeId, string Name, string? Position, string? Area, UserRole Roles, IReadOnlyList<OrgNodeDto> Reports);

public sealed record LookupDto(int Id, string Name);

// ── Configuración ────────────────────────────────────────────────────────────

public sealed class PolicySettingsDto
{
    [Range(0.25, 24)] public decimal OvertimeMinHours { get; set; } = 0.5m;
    [Range(0.5, 24)] public decimal OvertimeMaxHoursPerRequest { get; set; } = 12m;
    [Range(1, 300)] public decimal OvertimeMaxHoursPerMonth { get; set; } = 36m;
    [Range(0, 365)] public int OvertimeMaxDaysInPast { get; set; } = 30;
    [Range(0, 365)] public int RequestMaxDaysInFuture { get; set; } = 180;
    [Required] public string WorkingDays { get; set; } = "1,2,3,4,5";
    public bool VacationAllowNegativeBalance { get; set; }
    [Range(1, 60)] public int VacationMaxConsecutiveDays { get; set; } = 20;
    [Range(1, 240)] public int ReminderAfterHours { get; set; } = 24;
    [Range(1, 240)] public int UrgentAfterHours { get; set; } = 48;
    public bool RequireEmployeeSignature { get; set; }
    [Required, StringLength(200)] public string AdministrativeMailbox { get; set; } = "registro.administrativo@demo.timeflow.example";
    [StringLength(500)] public string? DocumentFooterText { get; set; } = "Documento generado por GPV Product TimeFlow. Firma electrónica simple: constancia de autorización interna; no equivale a firma electrónica avanzada.";
    [Required, StringLength(7)] public string BrandPrimaryColor { get; set; } = "#1F4FD8";
    [Range(1, 3650)] public int RetentionDays { get; set; } = 1825;
}

public sealed record HolidayDto(int Id, DateOnly Date, string Name, bool IsActive);
public sealed record LeaveCategoryDto(int Id, string Name, RequestKind AppliesTo, bool RequiresAttachment, bool IsActive);

// ── Auditoría, correo, exportación ───────────────────────────────────────────

public sealed record AuditEntryDto(long Id, DateTime OccurredAtUtc, string ActorName, string Action, string EntityType, string EntityId, string? Details, string? IpAddress, string Hash);

public sealed record AuditVerificationDto(bool IsValid, long EntriesChecked, long? FirstBrokenEntryId, string Message, DateTime VerifiedAtUtc);

public sealed record EmailOutboxDto(Guid Id, string To, string Subject, string EventType, EmailStatus Status, string StatusLabel, int Attempts, DateTime CreatedAtUtc, DateTime? SentAtUtc, string? LastError, string? Folio, string Provider);

public sealed class ExportFilter
{
    public DateOnly? From { get; set; }
    public DateOnly? To { get; set; }
    public int? EmployeeId { get; set; }
    public RequestKind? Kind { get; set; }
    /// <summary>approved | processed | all</summary>
    public string Set { get; set; } = "approved";
}

public sealed record ExcelExportLogDto(Guid Id, DateTime ExportedAtUtc, string ExportedByName, string FileName, int RowCount, string Filters, string Sha256);

public sealed record SystemHealthDto(
    string EnvironmentMode,
    string DatabaseProvider,
    bool DatabaseReachable,
    string EmailProvider,
    string AuthenticationMode,
    int PendingEmails,
    int FailedEmails,
    long AuditEntries,
    string Version,
    DateTime ServerTimeUtc,
    string TimeZone,
    long WorkingSetMb);

public sealed record SearchResultDto(string Kind, string Title, string Subtitle, string Link);

public sealed record VerificationDto(string Folio, string StatusLabel, string KindLabel, bool ContentIntact, int ValidSignatures, DateTime? LastDecisionUtc, string Message);
