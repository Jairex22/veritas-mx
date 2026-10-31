IF OBJECT_ID(N'[__EFMigrationsHistory]') IS NULL
BEGIN
    CREATE TABLE [__EFMigrationsHistory] (
        [MigrationId] nvarchar(150) NOT NULL,
        [ProductVersion] nvarchar(32) NOT NULL,
        CONSTRAINT [PK___EFMigrationsHistory] PRIMARY KEY ([MigrationId])
    );
END;
GO

BEGIN TRANSACTION;
IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [AuditLogs] (
        [Id] bigint NOT NULL IDENTITY,
        [Sequence] bigint NOT NULL,
        [OccurredAtUtc] datetime2 NOT NULL,
        [ActorEmployeeId] int NULL,
        [ActorName] nvarchar(500) NOT NULL,
        [Action] nvarchar(80) NOT NULL,
        [EntityType] nvarchar(500) NOT NULL,
        [EntityId] nvarchar(80) NOT NULL,
        [Details] nvarchar(max) NULL,
        [IpAddress] nvarchar(64) NULL,
        [PreviousHash] nvarchar(64) NOT NULL,
        [Hash] nvarchar(64) NOT NULL,
        CONSTRAINT [PK_AuditLogs] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Departments] (
        [Id] int NOT NULL IDENTITY,
        [Code] nvarchar(20) NOT NULL,
        [Name] nvarchar(120) NOT NULL,
        [IsActive] bit NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_Departments] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [EmailOutbox] (
        [Id] uniqueidentifier NOT NULL,
        [DeduplicationKey] nvarchar(250) NOT NULL,
        [ToAddresses] nvarchar(1000) NOT NULL,
        [CcAddresses] nvarchar(1000) NULL,
        [Subject] nvarchar(500) NOT NULL,
        [HtmlBody] nvarchar(max) NOT NULL,
        [EventType] nvarchar(500) NOT NULL,
        [RequestId] uniqueidentifier NULL,
        [Folio] nvarchar(500) NULL,
        [Status] int NOT NULL,
        [Attempts] int NOT NULL,
        [NextAttemptAtUtc] datetime2 NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [SentAtUtc] datetime2 NULL,
        [LastError] nvarchar(2000) NULL,
        [Provider] nvarchar(500) NOT NULL,
        [ProviderMessageId] nvarchar(500) NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_EmailOutbox] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [ExcelExports] (
        [Id] uniqueidentifier NOT NULL,
        [ExportedByEmployeeId] int NOT NULL,
        [ExportedByName] nvarchar(500) NOT NULL,
        [ExportedAtUtc] datetime2 NOT NULL,
        [FileName] nvarchar(500) NOT NULL,
        [Filters] nvarchar(1000) NOT NULL,
        [RowCount] int NOT NULL,
        [Sha256] nvarchar(500) NOT NULL,
        CONSTRAINT [PK_ExcelExports] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [FolioSequences] (
        [Year] int NOT NULL,
        [LastValue] int NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_FolioSequences] PRIMARY KEY ([Year])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Holidays] (
        [Id] int NOT NULL IDENTITY,
        [Date] date NOT NULL,
        [Name] nvarchar(120) NOT NULL,
        [IsActive] bit NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_Holidays] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [LeaveCategories] (
        [Id] int NOT NULL IDENTITY,
        [Name] nvarchar(100) NOT NULL,
        [AppliesTo] int NOT NULL,
        [RequiresAttachment] bit NOT NULL,
        [IsActive] bit NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_LeaveCategories] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Notifications] (
        [Id] uniqueidentifier NOT NULL,
        [RecipientEmployeeId] int NOT NULL,
        [Type] int NOT NULL,
        [Title] nvarchar(200) NOT NULL,
        [Message] nvarchar(500) NOT NULL,
        [RequestId] uniqueidentifier NULL,
        [Link] nvarchar(500) NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [ReadAtUtc] datetime2 NULL,
        [DeduplicationKey] nvarchar(120) NULL,
        CONSTRAINT [PK_Notifications] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Positions] (
        [Id] int NOT NULL IDENTITY,
        [Name] nvarchar(120) NOT NULL,
        [IsActive] bit NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_Positions] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [RequestTypes] (
        [Id] int NOT NULL IDENTITY,
        [Kind] int NOT NULL,
        [Name] nvarchar(500) NOT NULL,
        [Description] nvarchar(500) NOT NULL,
        [RequiresSignatureToApprove] bit NOT NULL,
        [IsActive] bit NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_RequestTypes] PRIMARY KEY ([Id])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [SystemSettings] (
        [Key] nvarchar(100) NOT NULL,
        [Value] nvarchar(2000) NOT NULL,
        [Description] nvarchar(500) NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [UpdatedByName] nvarchar(500) NULL,
        CONSTRAINT [PK_SystemSettings] PRIMARY KEY ([Key])
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Employees] (
        [Id] int NOT NULL IDENTITY,
        [EmployeeNumber] nvarchar(20) NOT NULL,
        [FullName] nvarchar(150) NOT NULL,
        [Email] nvarchar(200) NOT NULL,
        [NormalizedEmail] nvarchar(200) NOT NULL,
        [DepartmentId] int NOT NULL,
        [Area] nvarchar(100) NULL,
        [PositionId] int NULL,
        [HireDate] date NULL,
        [IsActive] bit NOT NULL,
        [IsSynthetic] bit NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_Employees] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_Employees_Departments_DepartmentId] FOREIGN KEY ([DepartmentId]) REFERENCES [Departments] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_Employees_Positions_PositionId] FOREIGN KEY ([PositionId]) REFERENCES [Positions] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [ReportingHierarchy] (
        [Id] int NOT NULL IDENTITY,
        [EmployeeId] int NOT NULL,
        [DirectSupervisorId] int NULL,
        [SeniorManagerId] int NULL,
        [EffectiveFrom] date NOT NULL,
        [EffectiveTo] date NULL,
        [IsCurrent] bit NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_ReportingHierarchy] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_ReportingHierarchy_Employees_DirectSupervisorId] FOREIGN KEY ([DirectSupervisorId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_ReportingHierarchy_Employees_EmployeeId] FOREIGN KEY ([EmployeeId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_ReportingHierarchy_Employees_SeniorManagerId] FOREIGN KEY ([SeniorManagerId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Requests] (
        [Id] uniqueidentifier NOT NULL,
        [Folio] nvarchar(20) NOT NULL,
        [EmployeeId] int NOT NULL,
        [RequestTypeId] int NOT NULL,
        [Kind] int NOT NULL,
        [Status] int NOT NULL,
        [Reason] nvarchar(500) NOT NULL,
        [Justification] nvarchar(1000) NULL,
        [Observations] nvarchar(1000) NULL,
        [LeaveCategoryId] int NULL,
        [IsFullDay] bit NOT NULL,
        [TotalHours] decimal(9,2) NOT NULL,
        [TotalDays] decimal(9,2) NOT NULL,
        [Version] int NOT NULL,
        [ContentHash] nvarchar(64) NOT NULL,
        [AssignedSupervisorId] int NULL,
        [AssignedManagerId] int NULL,
        [SubmittedAtUtc] datetime2 NULL,
        [StatusChangedAtUtc] datetime2 NULL,
        [ClosedAtUtc] datetime2 NULL,
        [LastReturnComment] nvarchar(1000) NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_Requests] PRIMARY KEY ([Id]),
        CONSTRAINT [CK_Requests_TotalDays] CHECK ([TotalDays] >= 0),
        CONSTRAINT [CK_Requests_TotalHours] CHECK ([TotalHours] >= 0),
        CONSTRAINT [CK_Requests_Version] CHECK ([Version] >= 1),
        CONSTRAINT [FK_Requests_Employees_AssignedManagerId] FOREIGN KEY ([AssignedManagerId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_Requests_Employees_AssignedSupervisorId] FOREIGN KEY ([AssignedSupervisorId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_Requests_Employees_EmployeeId] FOREIGN KEY ([EmployeeId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_Requests_LeaveCategories_LeaveCategoryId] FOREIGN KEY ([LeaveCategoryId]) REFERENCES [LeaveCategories] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_Requests_RequestTypes_RequestTypeId] FOREIGN KEY ([RequestTypeId]) REFERENCES [RequestTypes] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Users] (
        [Id] int NOT NULL IDENTITY,
        [EmployeeId] int NOT NULL,
        [Roles] int NOT NULL,
        [PasswordHash] nvarchar(200) NULL,
        [ExternalObjectId] nvarchar(100) NULL,
        [IsActive] bit NOT NULL,
        [FailedLoginCount] int NOT NULL,
        [LockoutEndUtc] datetime2 NULL,
        [LastLoginUtc] datetime2 NULL,
        [SecurityStamp] uniqueidentifier NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_Users] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_Users_Employees_EmployeeId] FOREIGN KEY ([EmployeeId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [VacationBalances] (
        [Id] int NOT NULL IDENTITY,
        [EmployeeId] int NOT NULL,
        [PeriodYear] int NOT NULL,
        [EntitledDays] decimal(9,2) NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_VacationBalances] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_VacationBalances_Employees_EmployeeId] FOREIGN KEY ([EmployeeId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [AdministrativeRegistrations] (
        [Id] int NOT NULL IDENTITY,
        [RequestId] uniqueidentifier NOT NULL,
        [ReceivedByEmployeeId] int NULL,
        [ReceivedByName] nvarchar(500) NULL,
        [ReceivedAtUtc] datetime2 NULL,
        [RegisteredByEmployeeId] int NULL,
        [RegisteredByName] nvarchar(500) NULL,
        [RegisteredAtUtc] datetime2 NULL,
        [ProcessedByEmployeeId] int NULL,
        [ProcessedByName] nvarchar(500) NULL,
        [ProcessedAtUtc] datetime2 NULL,
        [Observations] nvarchar(4000) NULL,
        [ExternalReference] nvarchar(100) NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [UpdatedAtUtc] datetime2 NOT NULL,
        [ConcurrencyStamp] uniqueidentifier NOT NULL,
        CONSTRAINT [PK_AdministrativeRegistrations] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_AdministrativeRegistrations_Requests_RequestId] FOREIGN KEY ([RequestId]) REFERENCES [Requests] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [ApprovalDecisions] (
        [Id] uniqueidentifier NOT NULL,
        [RequestId] uniqueidentifier NOT NULL,
        [ApprovalStepId] int NULL,
        [ActorEmployeeId] int NULL,
        [ActorName] nvarchar(150) NOT NULL,
        [Action] int NOT NULL,
        [FromStatus] int NOT NULL,
        [ToStatus] int NOT NULL,
        [Comment] nvarchar(1000) NULL,
        [RequestVersion] int NOT NULL,
        [OccurredAtUtc] datetime2 NOT NULL,
        [IdempotencyKey] nvarchar(80) NULL,
        CONSTRAINT [PK_ApprovalDecisions] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_ApprovalDecisions_Requests_RequestId] FOREIGN KEY ([RequestId]) REFERENCES [Requests] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [ApprovalSteps] (
        [Id] int NOT NULL IDENTITY,
        [RequestId] uniqueidentifier NOT NULL,
        [StepOrder] int NOT NULL,
        [Type] int NOT NULL,
        [AssigneeEmployeeId] int NULL,
        [Status] int NOT NULL,
        [ActorEmployeeId] int NULL,
        [ActedAtUtc] datetime2 NULL,
        [Comment] nvarchar(1000) NULL,
        [RequestVersion] int NOT NULL,
        CONSTRAINT [PK_ApprovalSteps] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_ApprovalSteps_Employees_AssigneeEmployeeId] FOREIGN KEY ([AssigneeEmployeeId]) REFERENCES [Employees] ([Id]) ON DELETE NO ACTION,
        CONSTRAINT [FK_ApprovalSteps_Requests_RequestId] FOREIGN KEY ([RequestId]) REFERENCES [Requests] ([Id]) ON DELETE CASCADE
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [Attachments] (
        [Id] uniqueidentifier NOT NULL,
        [RequestId] uniqueidentifier NOT NULL,
        [FileName] nvarchar(150) NOT NULL,
        [ContentType] nvarchar(120) NOT NULL,
        [SizeBytes] bigint NOT NULL,
        [Sha256] nvarchar(64) NOT NULL,
        [StorageKey] nvarchar(120) NOT NULL,
        [UploadedByEmployeeId] int NOT NULL,
        [UploadedByName] nvarchar(150) NOT NULL,
        [UploadedAtUtc] datetime2 NOT NULL,
        [IsDeleted] bit NOT NULL,
        CONSTRAINT [PK_Attachments] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_Attachments_Requests_RequestId] FOREIGN KEY ([RequestId]) REFERENCES [Requests] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [ElectronicSignatures] (
        [Id] uniqueidentifier NOT NULL,
        [RequestId] uniqueidentifier NOT NULL,
        [ApprovalDecisionId] uniqueidentifier NULL,
        [SignerEmployeeId] int NOT NULL,
        [SignerName] nvarchar(150) NOT NULL,
        [SignerRole] nvarchar(60) NOT NULL,
        [SignedAtUtc] datetime2 NOT NULL,
        [RequestVersion] int NOT NULL,
        [DocumentHash] nvarchar(64) NOT NULL,
        [SignatureHash] nvarchar(64) NOT NULL,
        [ImagePng] varbinary(max) NOT NULL,
        [IpAddress] nvarchar(64) NULL,
        [UserAgent] nvarchar(250) NULL,
        [IsValid] bit NOT NULL,
        [InvalidatedAtUtc] datetime2 NULL,
        [InvalidationReason] nvarchar(500) NULL,
        CONSTRAINT [PK_ElectronicSignatures] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_ElectronicSignatures_Requests_RequestId] FOREIGN KEY ([RequestId]) REFERENCES [Requests] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [OvertimeRecords] (
        [RequestId] uniqueidentifier NOT NULL,
        [EmployeeId] int NOT NULL,
        [WorkDate] date NOT NULL,
        [StartLocal] datetime2 NOT NULL,
        [EndLocal] datetime2 NOT NULL,
        [Hours] decimal(9,2) NOT NULL,
        [CrossesMidnight] bit NOT NULL,
        [Project] nvarchar(150) NULL,
        [Activity] nvarchar(1000) NULL,
        [PeriodYear] int NOT NULL,
        [PeriodMonth] int NOT NULL,
        CONSTRAINT [PK_OvertimeRecords] PRIMARY KEY ([RequestId]),
        CONSTRAINT [CK_OvertimeRecords_Hours] CHECK ([Hours] > 0),
        CONSTRAINT [FK_OvertimeRecords_Requests_RequestId] FOREIGN KEY ([RequestId]) REFERENCES [Requests] ([Id]) ON DELETE CASCADE
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [RequestPeriods] (
        [Id] int NOT NULL IDENTITY,
        [RequestId] uniqueidentifier NOT NULL,
        [StartDate] date NOT NULL,
        [EndDate] date NOT NULL,
        [StartTime] time NULL,
        [EndTime] time NULL,
        CONSTRAINT [PK_RequestPeriods] PRIMARY KEY ([Id]),
        CONSTRAINT [CK_RequestPeriods_Range] CHECK ([EndDate] >= [StartDate]),
        CONSTRAINT [FK_RequestPeriods_Requests_RequestId] FOREIGN KEY ([RequestId]) REFERENCES [Requests] ([Id]) ON DELETE CASCADE
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE TABLE [VacationTransactions] (
        [Id] uniqueidentifier NOT NULL,
        [VacationBalanceId] int NOT NULL,
        [RequestId] uniqueidentifier NULL,
        [Type] int NOT NULL,
        [Days] decimal(9,2) NOT NULL,
        [Description] nvarchar(500) NOT NULL,
        [CreatedByEmployeeId] int NULL,
        [CreatedByName] nvarchar(150) NOT NULL,
        [CreatedAtUtc] datetime2 NOT NULL,
        [DeduplicationKey] nvarchar(80) NULL,
        CONSTRAINT [PK_VacationTransactions] PRIMARY KEY ([Id]),
        CONSTRAINT [FK_VacationTransactions_VacationBalances_VacationBalanceId] FOREIGN KEY ([VacationBalanceId]) REFERENCES [VacationBalances] ([Id]) ON DELETE NO ACTION
    );
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_AdministrativeRegistrations_RequestId] ON [AdministrativeRegistrations] ([RequestId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ApprovalDecisions_ActorEmployeeId_OccurredAtUtc] ON [ApprovalDecisions] ([ActorEmployeeId], [OccurredAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    EXEC(N'CREATE UNIQUE INDEX [IX_ApprovalDecisions_RequestId_IdempotencyKey] ON [ApprovalDecisions] ([RequestId], [IdempotencyKey]) WHERE [IdempotencyKey] IS NOT NULL');
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ApprovalDecisions_RequestId_OccurredAtUtc] ON [ApprovalDecisions] ([RequestId], [OccurredAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ApprovalSteps_AssigneeEmployeeId_Status] ON [ApprovalSteps] ([AssigneeEmployeeId], [Status]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_ApprovalSteps_RequestId_RequestVersion_Type] ON [ApprovalSteps] ([RequestId], [RequestVersion], [Type]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Attachments_RequestId] ON [Attachments] ([RequestId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_AuditLogs_EntityType_EntityId] ON [AuditLogs] ([EntityType], [EntityId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_AuditLogs_OccurredAtUtc] ON [AuditLogs] ([OccurredAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_AuditLogs_Sequence] ON [AuditLogs] ([Sequence]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Departments_Code] ON [Departments] ([Code]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    EXEC(N'CREATE UNIQUE INDEX [IX_ElectronicSignatures_ApprovalDecisionId] ON [ElectronicSignatures] ([ApprovalDecisionId]) WHERE [ApprovalDecisionId] IS NOT NULL');
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ElectronicSignatures_RequestId] ON [ElectronicSignatures] ([RequestId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_EmailOutbox_DeduplicationKey] ON [EmailOutbox] ([DeduplicationKey]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_EmailOutbox_Status_NextAttemptAtUtc] ON [EmailOutbox] ([Status], [NextAttemptAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Employees_DepartmentId] ON [Employees] ([DepartmentId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Employees_EmployeeNumber] ON [Employees] ([EmployeeNumber]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Employees_FullName] ON [Employees] ([FullName]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Employees_NormalizedEmail] ON [Employees] ([NormalizedEmail]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Employees_PositionId] ON [Employees] ([PositionId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ExcelExports_ExportedAtUtc] ON [ExcelExports] ([ExportedAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Holidays_Date] ON [Holidays] ([Date]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    EXEC(N'CREATE UNIQUE INDEX [IX_Notifications_DeduplicationKey] ON [Notifications] ([DeduplicationKey]) WHERE [DeduplicationKey] IS NOT NULL');
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Notifications_RecipientEmployeeId_ReadAtUtc_CreatedAtUtc] ON [Notifications] ([RecipientEmployeeId], [ReadAtUtc], [CreatedAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_OvertimeRecords_EmployeeId_PeriodYear_PeriodMonth] ON [OvertimeRecords] ([EmployeeId], [PeriodYear], [PeriodMonth]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Positions_Name] ON [Positions] ([Name]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ReportingHierarchy_DirectSupervisorId_IsCurrent] ON [ReportingHierarchy] ([DirectSupervisorId], [IsCurrent]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ReportingHierarchy_EmployeeId_IsCurrent] ON [ReportingHierarchy] ([EmployeeId], [IsCurrent]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_ReportingHierarchy_SeniorManagerId_IsCurrent] ON [ReportingHierarchy] ([SeniorManagerId], [IsCurrent]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_RequestPeriods_RequestId] ON [RequestPeriods] ([RequestId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_RequestPeriods_StartDate_EndDate] ON [RequestPeriods] ([StartDate], [EndDate]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Requests_AssignedManagerId_Status] ON [Requests] ([AssignedManagerId], [Status]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Requests_AssignedSupervisorId_Status] ON [Requests] ([AssignedSupervisorId], [Status]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Requests_CreatedAtUtc] ON [Requests] ([CreatedAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Requests_EmployeeId_Status] ON [Requests] ([EmployeeId], [Status]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Requests_Folio] ON [Requests] ([Folio]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Requests_LeaveCategoryId] ON [Requests] ([LeaveCategoryId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Requests_RequestTypeId] ON [Requests] ([RequestTypeId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_Requests_Status_StatusChangedAtUtc] ON [Requests] ([Status], [StatusChangedAtUtc]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_RequestTypes_Kind] ON [RequestTypes] ([Kind]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_Users_EmployeeId] ON [Users] ([EmployeeId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    EXEC(N'CREATE UNIQUE INDEX [IX_Users_ExternalObjectId] ON [Users] ([ExternalObjectId]) WHERE [ExternalObjectId] IS NOT NULL');
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE UNIQUE INDEX [IX_VacationBalances_EmployeeId_PeriodYear] ON [VacationBalances] ([EmployeeId], [PeriodYear]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    EXEC(N'CREATE UNIQUE INDEX [IX_VacationTransactions_DeduplicationKey] ON [VacationTransactions] ([DeduplicationKey]) WHERE [DeduplicationKey] IS NOT NULL');
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_VacationTransactions_RequestId] ON [VacationTransactions] ([RequestId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    CREATE INDEX [IX_VacationTransactions_VacationBalanceId] ON [VacationTransactions] ([VacationBalanceId]);
END;

IF NOT EXISTS (
    SELECT * FROM [__EFMigrationsHistory]
    WHERE [MigrationId] = N'20261031144452_InitialCreate'
)
BEGIN
    INSERT INTO [__EFMigrationsHistory] ([MigrationId], [ProductVersion])
    VALUES (N'20261031144452_InitialCreate', N'10.0.14');
END;

COMMIT;
GO

