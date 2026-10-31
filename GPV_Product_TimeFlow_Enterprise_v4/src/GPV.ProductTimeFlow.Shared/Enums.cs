namespace GPV.ProductTimeFlow.Shared;

/// <summary>Tipos de solicitud administrados por Producto.</summary>
public enum RequestKind
{
    Overtime = 1,
    Vacation = 2,
    PaidLeave = 3,
    UnpaidLeave = 4
}

/// <summary>
/// Estados formales del flujo de tres filtros. Los valores numéricos se persisten:
/// NO reordenar ni reutilizar números.
/// </summary>
public enum RequestStatus
{
    Draft = 0,
    Submitted = 1,
    PendingSupervisor = 2,
    SupervisorApproved = 3,
    SupervisorRejected = 4,
    ReturnedForCorrection = 5,
    PendingManager = 6,
    ManagerApproved = 7,
    ManagerRejected = 8,
    PendingAdministrativeRegistration = 9,
    AdministrativeObserved = 10,
    AdministrativeRegistered = 11,
    Completed = 12,
    Cancelled = 13
}

/// <summary>Acciones que disparan transiciones en la máquina de estados.</summary>
public enum WorkflowAction
{
    Submit = 1,
    RouteToSupervisor = 2,
    SupervisorApprove = 3,
    SupervisorReject = 4,
    SupervisorReturn = 5,
    RouteToManager = 6,
    ManagerApprove = 7,
    ManagerReject = 8,
    ManagerReturn = 9,
    RouteToAdministrative = 10,
    AdministrativeObserve = 11,
    AdministrativeRegister = 12,
    Complete = 13,
    Cancel = 14,
    /// <summary>Acuse de recepción administrativa. No cambia el estado (no figura en la tabla de transiciones).</summary>
    AdministrativeReceive = 15
}

/// <summary>Decisión de un aprobador gerencial (filtros 1 y 2).</summary>
public enum ApprovalDecisionType
{
    Approve = 1,
    Reject = 2,
    Return = 3
}

public enum ApprovalStepType
{
    DirectSupervisor = 1,
    SeniorManager = 2,
    AdministrativeRegistration = 3
}

public enum ApprovalStepStatus
{
    Waiting = 0,
    Pending = 1,
    Approved = 2,
    Rejected = 3,
    Returned = 4,
    Invalidated = 5,
    Registered = 6,
    Cancelled = 7
}

/// <summary>Roles de la aplicación. Un usuario puede acumular varios.</summary>
[Flags]
public enum UserRole
{
    None = 0,
    Employee = 1,
    DirectSupervisor = 2,
    SeniorManager = 4,
    ProductAdmin = 8,
    AdministrativeRegistrar = 16
}

public enum AdministrativeAction
{
    Receive = 1,
    Observe = 2,
    Register = 3,
    Complete = 4
}

public enum EmailStatus
{
    Pending = 0,
    Sending = 1,
    Sent = 2,
    Failed = 3,
    /// <summary>Registrado por el proveedor de demostración: NO se envió a ningún buzón real.</summary>
    MockDelivered = 4,
    Skipped = 5
}

public enum VacationTransactionType
{
    Entitlement = 1,
    Consumption = 2,
    Reversal = 3,
    Adjustment = 4
}

public enum NotificationType
{
    RequestSubmitted = 1,
    RequestApproved = 2,
    RequestRejected = 3,
    RequestReturned = 4,
    RequestSigned = 5,
    RequestRegistered = 6,
    AdministrativeObservation = 7,
    PendingReminder = 8,
    RequestCompleted = 9,
    RequestCancelled = 10,
    SystemAlert = 11
}

public enum RequestScope
{
    Mine = 1,
    ApprovalInbox = 2,
    TeamHistory = 3,
    Administrative = 4,
    All = 5
}

public enum CalendarScope
{
    Mine = 1,
    Team = 2,
    Department = 3
}
