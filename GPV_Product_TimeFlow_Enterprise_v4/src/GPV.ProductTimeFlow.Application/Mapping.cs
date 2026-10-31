using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;
using Microsoft.EntityFrameworkCore;

namespace GPV.ProductTimeFlow.Application;

internal static class RequestLoading
{
    public static IQueryable<Request> WithSummary(this IQueryable<Request> q) =>
        q.Include(r => r.Employee).Include(r => r.Periods).Include(r => r.AssignedSupervisor).Include(r => r.AssignedManager);

    public static IQueryable<Request> WithDetail(this IQueryable<Request> q) =>
        q.Include(r => r.Employee).ThenInclude(e => e!.Department)
         .Include(r => r.Employee).ThenInclude(e => e!.Position)
         .Include(r => r.Periods).Include(r => r.Overtime)
         .Include(r => r.AssignedSupervisor).Include(r => r.AssignedManager)
         .Include(r => r.Steps).ThenInclude(s => s.Assignee)
         .Include(r => r.Decisions).Include(r => r.Signatures)
         .Include(r => r.Attachments).Include(r => r.Administrative)
         .Include(r => r.LeaveCategory).Include(r => r.RequestType)
         .AsSplitQuery();
}

internal static class DtoMapper
{
    public static RequestSummaryDto ToSummary(Request r, int urgentAfterHours = 48, DateTime? utcNow = null)
    {
        var p = r.PrimaryPeriod;
        string? approver = r.Status switch
        {
            RequestStatus.PendingSupervisor => r.AssignedSupervisor?.FullName,
            RequestStatus.PendingManager => r.AssignedManager?.FullName,
            RequestStatus.PendingAdministrativeRegistration or RequestStatus.AdministrativeObserved or RequestStatus.AdministrativeRegistered => "Registro administrativo",
            _ => null
        };
        var pending = r.Status is RequestStatus.PendingSupervisor or RequestStatus.PendingManager;
        var since = r.StatusChangedAtUtc ?? r.SubmittedAtUtc ?? r.CreatedAtUtc;
        return new RequestSummaryDto
        {
            Id = r.Id,
            Folio = r.Folio,
            Kind = r.Kind,
            Status = r.Status,
            EmployeeId = r.EmployeeId,
            EmployeeName = r.Employee?.FullName ?? "",
            EmployeeNumber = r.Employee?.EmployeeNumber ?? "",
            Area = r.Employee?.Area,
            StartDate = p?.StartDate ?? default,
            EndDate = p?.EndDate ?? default,
            StartTime = p?.StartTime,
            EndTime = p?.EndTime,
            IsFullDay = r.IsFullDay,
            Hours = r.TotalHours,
            Days = r.TotalDays,
            Reason = Text.Summarize(r.Reason),
            CreatedAtUtc = r.CreatedAtUtc,
            SubmittedAtUtc = r.SubmittedAtUtc,
            UpdatedAtUtc = r.UpdatedAtUtc,
            CurrentApproverName = approver,
            Version = r.Version,
            IsUrgent = pending && utcNow is not null && (utcNow.Value - since).TotalHours >= urgentAfterHours
        };
    }

    public static RequestDetailDto ToDetail(Request r, Actor actor, bool includeSignatureImages)
    {
        var employeeNames = new Dictionary<int, string>();
        void Remember(Employee? e) { if (e is not null) employeeNames[e.Id] = e.FullName; }
        Remember(r.Employee); Remember(r.AssignedSupervisor); Remember(r.AssignedManager);
        foreach (var s in r.Steps) Remember(s.Assignee);

        var currentSteps = r.Steps.Where(s => s.RequestVersion == r.Version).OrderBy(s => s.StepOrder).ToList();
        if (currentSteps.Count == 0) currentSteps = r.Steps.GroupBy(s => s.RequestVersion).OrderByDescending(g => g.Key).FirstOrDefault()?.OrderBy(s => s.StepOrder).ToList() ?? [];

        return new RequestDetailDto
        {
            Summary = ToSummary(r),
            EmployeeEmail = r.Employee?.Email,
            Department = r.Employee?.Department?.Name,
            Position = r.Employee?.Position?.Name,
            Project = r.Overtime?.Project,
            Activity = r.Overtime?.Activity,
            Justification = r.Justification,
            Observations = r.Observations,
            LeaveCategoryId = r.LeaveCategoryId,
            LeaveCategoryName = r.LeaveCategory?.Name,
            CrossesMidnight = r.Overtime?.CrossesMidnight ?? false,
            SupervisorName = r.AssignedSupervisor?.FullName,
            ManagerName = r.AssignedManager?.FullName,
            ContentHash = r.ContentHash,
            ReturnComment = r.Status == RequestStatus.ReturnedForCorrection ? r.LastReturnComment : null,
            Steps = currentSteps.Select(s => new ApprovalStepDto(s.StepOrder, s.Type, Labels.Step(s.Type), s.Status, Labels.StepStatus(s.Status),
                s.Type == ApprovalStepType.AdministrativeRegistration ? "Registro administrativo" : s.Assignee?.FullName,
                s.ActorEmployeeId is int a ? employeeNames.GetValueOrDefault(a) ?? r.Decisions.FirstOrDefault(d => d.ActorEmployeeId == a)?.ActorName : null,
                s.ActedAtUtc, s.Comment, s.RequestVersion)).ToList(),
            History = r.Decisions.OrderBy(d => d.OccurredAtUtc).ThenBy(d => (int)d.Action)
                .Select(d => new HistoryEntryDto(d.OccurredAtUtc, Labels.Action(d.Action), d.ActorName,
                    Labels.Status(d.FromStatus), Labels.Status(d.ToStatus), d.Comment, d.RequestVersion)).ToList(),
            Signatures = r.Signatures.OrderBy(s => s.SignedAtUtc).Select(s => new SignatureDto(s.Id, s.SignerName, s.SignerRole, s.SignedAtUtc,
                s.RequestVersion, s.DocumentHash, s.SignatureHash, s.IsValid, s.InvalidationReason, ElectronicSignature.SimpleElectronicSignature,
                includeSignatureImages && s.ImagePng.Length > 0 ? "data:image/png;base64," + Convert.ToBase64String(s.ImagePng) : null)).ToList(),
            Attachments = r.Attachments.Where(a => !a.IsDeleted).OrderBy(a => a.UploadedAtUtc)
                .Select(a => new AttachmentDto(a.Id, a.FileName, a.ContentType, a.SizeBytes, a.Sha256, a.UploadedByName, a.UploadedAtUtc)).ToList(),
            Administrative = r.Administrative is null ? null : new AdministrativeDto(r.Administrative.ReceivedByName, r.Administrative.ReceivedAtUtc,
                r.Administrative.RegisteredByName, r.Administrative.RegisteredAtUtc, r.Administrative.ProcessedByName, r.Administrative.ProcessedAtUtc,
                r.Administrative.Observations, r.Administrative.ExternalReference),
            Permissions = RequestAccess.Permissions(r, actor)
        };
    }

    public static NotificationDto ToDto(Notification n) =>
        new(n.Id, n.Type, n.Title, n.Message, n.RequestId, n.Link, n.CreatedAtUtc, n.ReadAtUtc is not null);
}
