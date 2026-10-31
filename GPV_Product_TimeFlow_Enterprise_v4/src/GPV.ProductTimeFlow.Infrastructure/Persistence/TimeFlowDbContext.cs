using GPV.ProductTimeFlow.Application;
using GPV.ProductTimeFlow.Domain;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace GPV.ProductTimeFlow.Infrastructure.Persistence;

/// <summary>
/// Contexto EF Core. Existen dos subclases (SQLite y SQL Server) solo para mantener migraciones separadas por proveedor.
/// </summary>
public abstract class TimeFlowDbContext(DbContextOptions options) : DbContext(options), ITimeFlowDbContext
{
    private static readonly SemaphoreSlim AuditLock = new(1, 1);

    public DbSet<Department> Departments => Set<Department>();
    public DbSet<Position> Positions => Set<Position>();
    public DbSet<Employee> Employees => Set<Employee>();
    public DbSet<UserAccount> Users => Set<UserAccount>();
    public DbSet<ReportingHierarchy> ReportingHierarchy => Set<ReportingHierarchy>();
    public DbSet<RequestType> RequestTypes => Set<RequestType>();
    public DbSet<LeaveCategory> LeaveCategories => Set<LeaveCategory>();
    public DbSet<Holiday> Holidays => Set<Holiday>();
    public DbSet<Request> Requests => Set<Request>();
    public DbSet<RequestPeriod> RequestPeriods => Set<RequestPeriod>();
    public DbSet<OvertimeRecord> OvertimeRecords => Set<OvertimeRecord>();
    public DbSet<ApprovalStep> ApprovalSteps => Set<ApprovalStep>();
    public DbSet<ApprovalDecision> ApprovalDecisions => Set<ApprovalDecision>();
    public DbSet<ElectronicSignature> ElectronicSignatures => Set<ElectronicSignature>();
    public DbSet<Attachment> Attachments => Set<Attachment>();
    public DbSet<VacationBalance> VacationBalances => Set<VacationBalance>();
    public DbSet<VacationTransaction> VacationTransactions => Set<VacationTransaction>();
    public DbSet<Notification> Notifications => Set<Notification>();
    public DbSet<EmailOutboxMessage> EmailOutbox => Set<EmailOutboxMessage>();
    public DbSet<AuditLog> AuditLogs => Set<AuditLog>();
    public DbSet<AdministrativeRegistration> AdministrativeRegistrations => Set<AdministrativeRegistration>();
    public DbSet<ExcelExport> ExcelExports => Set<ExcelExport>();
    public DbSet<SystemSetting> SystemSettings => Set<SystemSetting>();
    public DbSet<FolioSequence> FolioSequences => Set<FolioSequence>();

    public string ProviderName => Database.ProviderName?.Contains("Sqlite", StringComparison.OrdinalIgnoreCase) == true ? "SQLite" : "SQL Server";

    protected override void ConfigureConventions(ModelConfigurationBuilder builder)
    {
        builder.Properties<DateTime>().HaveConversion<UtcConverter>();
        builder.Properties<DateTime?>().HaveConversion<NullableUtcConverter>();
        builder.Properties<decimal>().HavePrecision(9, 2);
        builder.Properties<string>().HaveMaxLength(500);
    }

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Department>(e =>
        {
            e.HasIndex(x => x.Code).IsUnique();
            e.Property(x => x.Code).HasMaxLength(20);
            e.Property(x => x.Name).HasMaxLength(120);
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        });
        b.Entity<Position>(e => { e.Property(x => x.Name).HasMaxLength(120); e.HasIndex(x => x.Name).IsUnique(); e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken(); });

        b.Entity<Employee>(e =>
        {
            e.HasIndex(x => x.EmployeeNumber).IsUnique();
            e.HasIndex(x => x.NormalizedEmail).IsUnique();
            e.HasIndex(x => x.FullName);
            e.Property(x => x.EmployeeNumber).HasMaxLength(20);
            e.Property(x => x.FullName).HasMaxLength(150);
            e.Property(x => x.Email).HasMaxLength(200);
            e.Property(x => x.NormalizedEmail).HasMaxLength(200);
            e.Property(x => x.Area).HasMaxLength(100);
            e.HasOne(x => x.Department).WithMany().HasForeignKey(x => x.DepartmentId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.Position).WithMany().HasForeignKey(x => x.PositionId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.User).WithOne(u => u.Employee).HasForeignKey<UserAccount>(u => u.EmployeeId).OnDelete(DeleteBehavior.Restrict);
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
            e.Ignore(x => x.FirstName);
        });

        b.Entity<UserAccount>(e =>
        {
            e.ToTable("Users");
            e.HasIndex(x => x.EmployeeId).IsUnique();
            e.HasIndex(x => x.ExternalObjectId).IsUnique();
            e.Property(x => x.PasswordHash).HasMaxLength(200);
            e.Property(x => x.ExternalObjectId).HasMaxLength(100);
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        });

        b.Entity<ReportingHierarchy>(e =>
        {
            e.ToTable("ReportingHierarchy");
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.DirectSupervisor).WithMany().HasForeignKey(x => x.DirectSupervisorId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.SeniorManager).WithMany().HasForeignKey(x => x.SeniorManagerId).OnDelete(DeleteBehavior.Restrict);
            e.HasIndex(x => new { x.EmployeeId, x.IsCurrent });
            e.HasIndex(x => new { x.DirectSupervisorId, x.IsCurrent });
            e.HasIndex(x => new { x.SeniorManagerId, x.IsCurrent });
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        });

        b.Entity<RequestType>(e => { e.HasIndex(x => x.Kind).IsUnique(); e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken(); });
        b.Entity<LeaveCategory>(e => { e.Property(x => x.Name).HasMaxLength(100); e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken(); });
        b.Entity<Holiday>(e => { e.HasIndex(x => x.Date).IsUnique(); e.Property(x => x.Name).HasMaxLength(120); e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken(); });

        b.Entity<Request>(e =>
        {
            e.HasIndex(x => x.Folio).IsUnique();
            e.HasIndex(x => new { x.EmployeeId, x.Status });
            e.HasIndex(x => new { x.AssignedSupervisorId, x.Status });
            e.HasIndex(x => new { x.AssignedManagerId, x.Status });
            e.HasIndex(x => new { x.Status, x.StatusChangedAtUtc });
            e.HasIndex(x => x.CreatedAtUtc);
            e.Property(x => x.Folio).HasMaxLength(20);
            e.Property(x => x.Reason).HasMaxLength(500);
            e.Property(x => x.Justification).HasMaxLength(1000);
            e.Property(x => x.Observations).HasMaxLength(1000);
            e.Property(x => x.LastReturnComment).HasMaxLength(1000);
            e.Property(x => x.ContentHash).HasMaxLength(64);
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.AssignedSupervisor).WithMany().HasForeignKey(x => x.AssignedSupervisorId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.AssignedManager).WithMany().HasForeignKey(x => x.AssignedManagerId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.RequestType).WithMany().HasForeignKey(x => x.RequestTypeId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.LeaveCategory).WithMany().HasForeignKey(x => x.LeaveCategoryId).OnDelete(DeleteBehavior.Restrict);
            e.HasMany(x => x.Periods).WithOne().HasForeignKey(p => p.RequestId).OnDelete(DeleteBehavior.Cascade);
            e.HasOne(x => x.Overtime).WithOne().HasForeignKey<OvertimeRecord>(o => o.RequestId).OnDelete(DeleteBehavior.Cascade);
            e.HasMany(x => x.Steps).WithOne().HasForeignKey(s => s.RequestId).OnDelete(DeleteBehavior.Cascade);
            e.HasMany(x => x.Decisions).WithOne().HasForeignKey(s => s.RequestId).OnDelete(DeleteBehavior.Restrict);
            e.HasMany(x => x.Signatures).WithOne().HasForeignKey(s => s.RequestId).OnDelete(DeleteBehavior.Restrict);
            e.HasMany(x => x.Attachments).WithOne().HasForeignKey(s => s.RequestId).OnDelete(DeleteBehavior.Restrict);
            e.HasOne(x => x.Administrative).WithOne().HasForeignKey<AdministrativeRegistration>(a => a.RequestId).OnDelete(DeleteBehavior.Restrict);
            e.Ignore(x => x.PrimaryPeriod);
            e.ToTable(t =>
            {
                t.HasCheckConstraint("CK_Requests_TotalHours", "[TotalHours] >= 0");
                t.HasCheckConstraint("CK_Requests_TotalDays", "[TotalDays] >= 0");
                t.HasCheckConstraint("CK_Requests_Version", "[Version] >= 1");
            });
        });

        b.Entity<RequestPeriod>(e =>
        {
            e.HasIndex(x => new { x.StartDate, x.EndDate });
            e.ToTable("RequestPeriods", t => t.HasCheckConstraint("CK_RequestPeriods_Range", "[EndDate] >= [StartDate]"));
        });

        b.Entity<OvertimeRecord>(e =>
        {
            e.HasKey(x => x.RequestId);
            e.HasIndex(x => new { x.EmployeeId, x.PeriodYear, x.PeriodMonth });
            e.Property(x => x.Project).HasMaxLength(150);
            e.Property(x => x.Activity).HasMaxLength(1000);
            e.ToTable("OvertimeRecords", t => t.HasCheckConstraint("CK_OvertimeRecords_Hours", "[Hours] > 0"));
        });

        b.Entity<ApprovalStep>(e =>
        {
            e.HasIndex(x => new { x.RequestId, x.RequestVersion, x.Type }).IsUnique();
            e.HasIndex(x => new { x.AssigneeEmployeeId, x.Status });
            e.HasOne(x => x.Assignee).WithMany().HasForeignKey(x => x.AssigneeEmployeeId).OnDelete(DeleteBehavior.Restrict);
            e.Property(x => x.Comment).HasMaxLength(1000);
        });

        b.Entity<ApprovalDecision>(e =>
        {
            e.HasIndex(x => new { x.RequestId, x.IdempotencyKey }).IsUnique();
            e.HasIndex(x => new { x.RequestId, x.OccurredAtUtc });
            e.HasIndex(x => new { x.ActorEmployeeId, x.OccurredAtUtc });
            e.Property(x => x.Comment).HasMaxLength(1000);
            e.Property(x => x.ActorName).HasMaxLength(150);
            e.Property(x => x.IdempotencyKey).HasMaxLength(80);
        });

        b.Entity<ElectronicSignature>(e =>
        {
            e.HasIndex(x => x.RequestId);
            e.HasIndex(x => x.ApprovalDecisionId).IsUnique();
            e.Property(x => x.ImagePng).HasMaxLength(400 * 1024);
            e.Property(x => x.DocumentHash).HasMaxLength(64);
            e.Property(x => x.SignatureHash).HasMaxLength(64);
            e.Property(x => x.SignerName).HasMaxLength(150);
            e.Property(x => x.SignerRole).HasMaxLength(60);
            e.Property(x => x.UserAgent).HasMaxLength(250);
            e.Property(x => x.IpAddress).HasMaxLength(64);
        });

        b.Entity<Attachment>(e =>
        {
            e.HasIndex(x => x.RequestId);
            e.Property(x => x.FileName).HasMaxLength(150);
            e.Property(x => x.ContentType).HasMaxLength(120);
            e.Property(x => x.Sha256).HasMaxLength(64);
            e.Property(x => x.StorageKey).HasMaxLength(120);
            e.Property(x => x.UploadedByName).HasMaxLength(150);
        });

        b.Entity<VacationBalance>(e =>
        {
            e.HasIndex(x => new { x.EmployeeId, x.PeriodYear }).IsUnique();
            e.HasOne(x => x.Employee).WithMany().HasForeignKey(x => x.EmployeeId).OnDelete(DeleteBehavior.Restrict);
            e.HasMany(x => x.Transactions).WithOne().HasForeignKey(t => t.VacationBalanceId).OnDelete(DeleteBehavior.Restrict);
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        });
        b.Entity<VacationTransaction>(e =>
        {
            e.HasIndex(x => x.DeduplicationKey).IsUnique();
            e.HasIndex(x => x.RequestId);
            e.Property(x => x.DeduplicationKey).HasMaxLength(80);
            e.Property(x => x.CreatedByName).HasMaxLength(150);
        });

        b.Entity<Notification>(e =>
        {
            e.HasIndex(x => new { x.RecipientEmployeeId, x.ReadAtUtc, x.CreatedAtUtc });
            e.HasIndex(x => x.DeduplicationKey).IsUnique();
            e.Property(x => x.Title).HasMaxLength(200);
            e.Property(x => x.DeduplicationKey).HasMaxLength(120);
        });

        b.Entity<EmailOutboxMessage>(e =>
        {
            e.ToTable("EmailOutbox");
            e.HasIndex(x => x.DeduplicationKey).IsUnique();
            e.HasIndex(x => new { x.Status, x.NextAttemptAtUtc });
            e.Property(x => x.DeduplicationKey).HasMaxLength(250);
            e.Property(x => x.HtmlBody).HasMaxLength(64 * 1024);
            e.Property(x => x.LastError).HasMaxLength(2000);
            e.Property(x => x.ToAddresses).HasMaxLength(1000);
            e.Property(x => x.CcAddresses).HasMaxLength(1000);
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        });

        b.Entity<AuditLog>(e =>
        {
            e.HasIndex(x => x.Sequence).IsUnique();
            e.HasIndex(x => new { x.EntityType, x.EntityId });
            e.HasIndex(x => x.OccurredAtUtc);
            e.Property(x => x.Details).HasMaxLength(8000);
            e.Property(x => x.Hash).HasMaxLength(64);
            e.Property(x => x.PreviousHash).HasMaxLength(64);
            e.Property(x => x.Action).HasMaxLength(80);
            e.Property(x => x.EntityId).HasMaxLength(80);
            e.Property(x => x.IpAddress).HasMaxLength(64);
        });

        b.Entity<AdministrativeRegistration>(e =>
        {
            e.HasIndex(x => x.RequestId).IsUnique();
            e.Property(x => x.Observations).HasMaxLength(4000);
            e.Property(x => x.ExternalReference).HasMaxLength(100);
            e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken();
        });

        b.Entity<ExcelExport>(e => { e.HasIndex(x => x.ExportedAtUtc); e.Property(x => x.Filters).HasMaxLength(1000); });
        b.Entity<SystemSetting>(e => { e.HasKey(x => x.Key); e.Property(x => x.Key).HasMaxLength(100); e.Property(x => x.Value).HasMaxLength(2000); });
        b.Entity<FolioSequence>(e => { e.HasKey(x => x.Year); e.Property(x => x.Year).ValueGeneratedNever(); e.Property(x => x.ConcurrencyStamp).IsConcurrencyToken(); });

        // Las claves Guid las asigna la aplicación: así EF trata como "nuevas" las entidades descubiertas por navegación.
        foreach (var entity in b.Model.GetEntityTypes())
        foreach (var key in entity.GetKeys().Where(k => k.IsPrimaryKey()))
        foreach (var prop in key.Properties.Where(p => p.ClrType == typeof(Guid)))
            prop.ValueGenerated = Microsoft.EntityFrameworkCore.Metadata.ValueGenerated.Never;
    }

    public override int SaveChanges(bool acceptAllChangesOnSuccess) =>
        SaveChangesAsync(acceptAllChangesOnSuccess).GetAwaiter().GetResult();

    public override async Task<int> SaveChangesAsync(bool acceptAllChangesOnSuccess, CancellationToken cancellationToken = default)
    {
        EnforceImmutability();
        StampEntities();
        var audits = ChangeTracker.Entries<AuditLog>().Where(e => e.State == EntityState.Added).Select(e => e.Entity).ToList();
        if (audits.Count == 0) return await base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);

        // Encadenamiento: cada registro contiene el hash del anterior. Se serializa para mantener el orden.
        await AuditLock.WaitAsync(cancellationToken);
        try
        {
            var last = await AuditLogs.AsNoTracking().OrderByDescending(a => a.Sequence).Select(a => new { a.Sequence, a.Hash }).FirstOrDefaultAsync(cancellationToken);
            var next = (last?.Sequence ?? 0) + 1;
            var previous = last?.Hash ?? "";
            foreach (var a in audits)
            {
                a.Sequence = next++;
                a.PreviousHash = previous;
                a.Hash = AuditHasher.Compute(a);
                previous = a.Hash;
            }
            return await base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
        }
        finally { AuditLock.Release(); }
    }

    private void EnforceImmutability()
    {
        foreach (var entry in ChangeTracker.Entries())
        {
            if (entry.State is not (EntityState.Modified or EntityState.Deleted)) continue;
            if (entry.Entity is AuditLog or ApprovalDecision or VacationTransaction)
                throw new InvalidOperationException($"{entry.Entity.GetType().Name} es inmutable: no se permite modificar ni eliminar registros.");
            if (entry.Entity is ElectronicSignature && (entry.State == EntityState.Deleted
                || entry.Properties.Any(p => p.IsModified && p.Metadata.Name is not (nameof(ElectronicSignature.IsValid) or nameof(ElectronicSignature.InvalidatedAtUtc) or nameof(ElectronicSignature.InvalidationReason)))))
                throw new InvalidOperationException("Una firma electrónica solo puede invalidarse; su contenido no puede modificarse.");
        }
    }

    private void StampEntities()
    {
        var now = DateTime.UtcNow;
        foreach (var entry in ChangeTracker.Entries<TrackedEntity>())
        {
            if (entry.State == EntityState.Added)
            {
                entry.Entity.CreatedAtUtc = entry.Entity.CreatedAtUtc == default ? now : entry.Entity.CreatedAtUtc;
                entry.Entity.UpdatedAtUtc = now;
                entry.Entity.ConcurrencyStamp = Guid.NewGuid();
            }
            else if (entry.State == EntityState.Modified)
            {
                entry.Entity.UpdatedAtUtc = now;
                entry.Entity.ConcurrencyStamp = Guid.NewGuid();
            }
        }
        // Una solicitud cuyo detalle cambió también renueva su token (protege contra decisiones simultáneas).
        foreach (var request in ChangeTracker.Entries<Request>().Where(e => e.State == EntityState.Unchanged))
        {
            var touched = ChangeTracker.Entries().Any(e => e.State != EntityState.Unchanged && e.Entity switch
            {
                ApprovalStep s => s.RequestId == request.Entity.Id,
                ApprovalDecision d => d.RequestId == request.Entity.Id,
                ElectronicSignature g => g.RequestId == request.Entity.Id,
                AdministrativeRegistration a => a.RequestId == request.Entity.Id,
                _ => false
            });
            if (touched) { request.Entity.UpdatedAtUtc = now; request.Entity.ConcurrencyStamp = Guid.NewGuid(); request.State = EntityState.Modified; }
        }
    }

    private sealed class UtcConverter() : ValueConverter<DateTime, DateTime>(v => v.Kind == DateTimeKind.Utc ? v : DateTime.SpecifyKind(v, DateTimeKind.Utc), v => DateTime.SpecifyKind(v, DateTimeKind.Utc));
    private sealed class NullableUtcConverter() : ValueConverter<DateTime?, DateTime?>(
        v => v.HasValue ? (v.Value.Kind == DateTimeKind.Utc ? v : DateTime.SpecifyKind(v.Value, DateTimeKind.Utc)) : v,
        v => v.HasValue ? DateTime.SpecifyKind(v.Value, DateTimeKind.Utc) : v);
}

public sealed class SqliteTimeFlowDbContext(DbContextOptions<SqliteTimeFlowDbContext> options) : TimeFlowDbContext(options);
public sealed class SqlServerTimeFlowDbContext(DbContextOptions<SqlServerTimeFlowDbContext> options) : TimeFlowDbContext(options);
