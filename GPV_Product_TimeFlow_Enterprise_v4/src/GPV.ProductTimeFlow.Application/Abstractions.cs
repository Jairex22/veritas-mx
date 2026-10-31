using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

namespace GPV.ProductTimeFlow.Application;

/// <summary>Puerto de persistencia. Implementado por EF Core en Infrastructure.</summary>
public interface ITimeFlowDbContext
{
    DbSet<Department> Departments { get; }
    DbSet<Position> Positions { get; }
    DbSet<Employee> Employees { get; }
    DbSet<UserAccount> Users { get; }
    DbSet<ReportingHierarchy> ReportingHierarchy { get; }
    DbSet<RequestType> RequestTypes { get; }
    DbSet<LeaveCategory> LeaveCategories { get; }
    DbSet<Holiday> Holidays { get; }
    DbSet<Request> Requests { get; }
    DbSet<RequestPeriod> RequestPeriods { get; }
    DbSet<OvertimeRecord> OvertimeRecords { get; }
    DbSet<ApprovalStep> ApprovalSteps { get; }
    DbSet<ApprovalDecision> ApprovalDecisions { get; }
    DbSet<ElectronicSignature> ElectronicSignatures { get; }
    DbSet<Attachment> Attachments { get; }
    DbSet<VacationBalance> VacationBalances { get; }
    DbSet<VacationTransaction> VacationTransactions { get; }
    DbSet<Notification> Notifications { get; }
    DbSet<EmailOutboxMessage> EmailOutbox { get; }
    DbSet<AuditLog> AuditLogs { get; }
    DbSet<AdministrativeRegistration> AdministrativeRegistrations { get; }
    DbSet<ExcelExport> ExcelExports { get; }
    DbSet<SystemSetting> SystemSettings { get; }
    DbSet<FolioSequence> FolioSequences { get; }
    DatabaseFacade Database { get; }
    Task<int> SaveChangesAsync(CancellationToken cancellationToken = default);
    string ProviderName { get; }
}

/// <summary>Identidad autenticada que ejecuta una operación. Se construye en cada host a partir de los claims.</summary>
public sealed record Actor(int EmployeeId, string Name, UserRole Roles, string? IpAddress = null, string? UserAgent = null)
{
    public bool Has(UserRole role) => (Roles & role) == role;
    public static Actor System { get; } = new(0, "Sistema TimeFlow", UserRole.None);
}

public enum EnvironmentMode { Demo, Test, Production }

public sealed class TimeFlowOptions
{
    public const string Section = "TimeFlow";
    public EnvironmentMode Mode { get; set; } = EnvironmentMode.Demo;
    /// <summary>URL pública de la aplicación web; se usa en correos y QR de verificación.</summary>
    public string PublicBaseUrl { get; set; } = "https://localhost:5001";
    public string TimeZoneId { get; set; } = "America/Mexico_City";
    public string AttachmentsPath { get; set; } = "App_Data/attachments";
    public long MaxAttachmentBytes { get; set; } = 10 * 1024 * 1024;
    public int MaxAttachmentsPerRequest { get; set; } = 10;
}

/// <summary>Reloj con zona horaria corporativa. Todos los instantes se persisten en UTC.</summary>
public sealed class LocalClock(TimeProvider time, Microsoft.Extensions.Options.IOptions<TimeFlowOptions> options)
{
    private readonly TimeZoneInfo _zone = ResolveZone(options.Value.TimeZoneId);
    public DateTime UtcNow => time.GetUtcNow().UtcDateTime;
    public DateTime LocalNow => TimeZoneInfo.ConvertTimeFromUtc(UtcNow, _zone);
    public DateOnly Today => DateOnly.FromDateTime(LocalNow);
    public TimeZoneInfo Zone => _zone;
    public DateTime ToLocal(DateTime utc) => TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc, DateTimeKind.Utc), _zone);

    private static TimeZoneInfo ResolveZone(string id)
    {
        try { return TimeZoneInfo.FindSystemTimeZoneById(id); }
        catch (TimeZoneNotFoundException) { return TimeZoneInfo.FindSystemTimeZoneById("Central Standard Time (Mexico)"); }
    }
}

public sealed record StoredFile(string StorageKey, long SizeBytes, string Sha256);

public interface IFileStorage
{
    Task<StoredFile> SaveAsync(Stream content, string extension, CancellationToken ct);
    Task<Stream?> OpenReadAsync(string storageKey, CancellationToken ct);
}

public interface IPdfRenderer
{
    byte[] RenderRequest(RequestDocumentModel model);
}

public sealed record RequestDocumentModel(
    RequestDetailDto Detail,
    string VerificationUrl,
    byte[] QrPng,
    IReadOnlyDictionary<Guid, byte[]> SignatureImages,
    string FooterText,
    DateTime GeneratedAtLocal,
    string GeneratedBy,
    string TimeZoneLabel,
    string EnvironmentLabel);

public sealed record ExportRow(
    string Folio, DateTime CreatedAtLocal, string EmployeeNumber, string EmployeeName, string Department, string Area, string Type,
    DateOnly StartDate, DateOnly EndDate, decimal Hours, decimal Days, string Reason,
    string? SupervisorName, DateTime? SupervisorApprovedAtLocal, string? ManagerName, DateTime? ManagerApprovedAtLocal,
    string AdministrativeStatus, DateTime? RegisteredAtLocal, string? Observations, Guid Id);

public sealed record ExportMetadata(string GeneratedBy, DateTime GeneratedAtLocal, string Filters, string EnvironmentLabel, string TimeZone);

public interface IExcelExporter
{
    byte[] ExportRequests(IReadOnlyList<ExportRow> rows, ExportMetadata metadata);
    byte[] EmployeeImportTemplate();
}

public sealed record EmployeeImportRow(int RowNumber, string? EmployeeNumber, string? FullName, string? Email, string? Department,
    string? Area, string? Position, string? SupervisorEmail, string? ManagerEmail, string? Roles, DateOnly? HireDate, decimal? VacationDays);

public interface IExcelImporter
{
    IReadOnlyList<EmployeeImportRow> ReadEmployees(Stream workbook);
}

public interface IQrCodeGenerator
{
    byte[] Png(string content);
}

/// <summary>Empuja notificaciones en tiempo real (SignalR y bus interno de Blazor). Opcional: la fuente de verdad es la BD.</summary>
public interface IRealtimeNotifier
{
    Task PushAsync(IReadOnlyCollection<(int EmployeeId, NotificationDto Notification)> items, CancellationToken ct);
}

public sealed record EmailModel(
    string Title,
    string Intro,
    string Folio,
    string EmployeeName,
    string RequestType,
    string Dates,
    string Duration,
    string ReasonSummary,
    string Status,
    string? Approver,
    string Link,
    string? Comment,
    string EnvironmentLabel);

public interface IEmailComposer
{
    (string Subject, string Html) Compose(EmailModel model);
}

public interface IPasswordService
{
    string Hash(string password);
    bool Verify(string hash, string password);
}
