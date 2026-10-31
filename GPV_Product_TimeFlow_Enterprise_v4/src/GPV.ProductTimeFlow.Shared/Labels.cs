namespace GPV.ProductTimeFlow.Shared;

/// <summary>
/// Textos en español de México para todo lo que ve el usuario.
/// Los nombres técnicos (enums en inglés) nunca deben mostrarse en la interfaz.
/// </summary>
public static class Labels
{
    public static string Status(RequestStatus status) => status switch
    {
        RequestStatus.Draft => "Borrador",
        RequestStatus.Submitted => "Enviada",
        RequestStatus.PendingSupervisor => "Pendiente de jefa directa",
        RequestStatus.SupervisorApproved => "Aprobada por jefa directa",
        RequestStatus.SupervisorRejected => "Rechazada por jefa directa",
        RequestStatus.ReturnedForCorrection => "Devuelta para corrección",
        RequestStatus.PendingManager => "Pendiente de jefe superior",
        RequestStatus.ManagerApproved => "Aprobada por jefe superior",
        RequestStatus.ManagerRejected => "Rechazada por jefe superior",
        RequestStatus.PendingAdministrativeRegistration => "Pendiente de registro administrativo",
        RequestStatus.AdministrativeObserved => "Con observaciones administrativas",
        RequestStatus.AdministrativeRegistered => "Registrada administrativamente",
        RequestStatus.Completed => "Completada",
        RequestStatus.Cancelled => "Cancelada",
        _ => "Desconocido"
    };

    /// <summary>Categoría visual del estado (para chips de color).</summary>
    public static string StatusTone(RequestStatus status) => status switch
    {
        RequestStatus.Draft => "neutral",
        RequestStatus.Submitted or RequestStatus.PendingSupervisor or RequestStatus.PendingManager => "warning",
        RequestStatus.SupervisorApproved or RequestStatus.ManagerApproved => "info",
        RequestStatus.PendingAdministrativeRegistration or RequestStatus.AdministrativeRegistered => "info",
        RequestStatus.AdministrativeObserved or RequestStatus.ReturnedForCorrection => "attention",
        RequestStatus.SupervisorRejected or RequestStatus.ManagerRejected => "danger",
        RequestStatus.Completed => "success",
        RequestStatus.Cancelled => "muted",
        _ => "neutral"
    };

    public static string Kind(RequestKind kind) => kind switch
    {
        RequestKind.Overtime => "Tiempo extra",
        RequestKind.Vacation => "Vacaciones",
        RequestKind.PaidLeave => "Permiso con goce de sueldo",
        RequestKind.UnpaidLeave => "Permiso sin goce de sueldo",
        _ => "Solicitud"
    };

    public static string KindShort(RequestKind kind) => kind switch
    {
        RequestKind.Overtime => "Tiempo extra",
        RequestKind.Vacation => "Vacaciones",
        RequestKind.PaidLeave => "Con goce",
        RequestKind.UnpaidLeave => "Sin goce",
        _ => "Solicitud"
    };

    public static string Role(UserRole role) => role switch
    {
        UserRole.Employee => "Empleado",
        UserRole.DirectSupervisor => "Jefa directa",
        UserRole.SeniorManager => "Jefe superior",
        UserRole.ProductAdmin => "Administrador de Producto",
        UserRole.AdministrativeRegistrar => "Registro administrativo",
        _ => "Sin rol"
    };

    public static IEnumerable<string> Roles(UserRole roles) =>
        Enum.GetValues<UserRole>().Where(r => r != UserRole.None && roles.HasFlag(r)).Select(Role);

    public static string Decision(ApprovalDecisionType decision) => decision switch
    {
        ApprovalDecisionType.Approve => "Aprobada",
        ApprovalDecisionType.Reject => "Rechazada",
        ApprovalDecisionType.Return => "Devuelta para corrección",
        _ => "—"
    };

    public static string Step(ApprovalStepType step) => step switch
    {
        ApprovalStepType.DirectSupervisor => "Filtro 1 · Jefa directa",
        ApprovalStepType.SeniorManager => "Filtro 2 · Jefe superior",
        ApprovalStepType.AdministrativeRegistration => "Filtro 3 · Registro administrativo",
        _ => "Filtro"
    };

    public static string StepStatus(ApprovalStepStatus status) => status switch
    {
        ApprovalStepStatus.Waiting => "En espera",
        ApprovalStepStatus.Pending => "Pendiente",
        ApprovalStepStatus.Approved => "Aprobado",
        ApprovalStepStatus.Rejected => "Rechazado",
        ApprovalStepStatus.Returned => "Devuelto",
        ApprovalStepStatus.Invalidated => "Invalidado por cambios",
        ApprovalStepStatus.Registered => "Registrado",
        ApprovalStepStatus.Cancelled => "Cancelado",
        _ => "—"
    };

    public static string Action(WorkflowAction action) => action switch
    {
        WorkflowAction.Submit => "Envío de solicitud",
        WorkflowAction.RouteToSupervisor => "Turnada a jefa directa",
        WorkflowAction.SupervisorApprove => "Aprobación de jefa directa",
        WorkflowAction.SupervisorReject => "Rechazo de jefa directa",
        WorkflowAction.SupervisorReturn => "Devolución de jefa directa",
        WorkflowAction.RouteToManager => "Turnada a jefe superior",
        WorkflowAction.ManagerApprove => "Aprobación de jefe superior",
        WorkflowAction.ManagerReject => "Rechazo de jefe superior",
        WorkflowAction.ManagerReturn => "Devolución de jefe superior",
        WorkflowAction.RouteToAdministrative => "Remitida a registro administrativo",
        WorkflowAction.AdministrativeObserve => "Observación administrativa",
        WorkflowAction.AdministrativeRegister => "Registro administrativo",
        WorkflowAction.Complete => "Marcada como procesada",
        WorkflowAction.Cancel => "Cancelación",
        WorkflowAction.AdministrativeReceive => "Recepción administrativa",
        _ => action.ToString()
    };

    public static string EmailStatus(EmailStatus status) => status switch
    {
        Shared.EmailStatus.Pending => "En cola",
        Shared.EmailStatus.Sending => "Enviando",
        Shared.EmailStatus.Sent => "Enviado (Microsoft Graph)",
        Shared.EmailStatus.Failed => "Fallido",
        Shared.EmailStatus.MockDelivered => "Registrado en buzón DEMO (no enviado)",
        Shared.EmailStatus.Skipped => "Omitido",
        _ => "—"
    };

    public static string AdministrativeAction(AdministrativeAction action) => action switch
    {
        Shared.AdministrativeAction.Receive => "Marcada como recibida",
        Shared.AdministrativeAction.Observe => "Observación registrada",
        Shared.AdministrativeAction.Register => "Registrada administrativamente",
        Shared.AdministrativeAction.Complete => "Marcada como procesada",
        _ => "—"
    };

    public static string VacationTransaction(VacationTransactionType type) => type switch
    {
        VacationTransactionType.Entitlement => "Asignación del periodo",
        VacationTransactionType.Consumption => "Descuento por solicitud autorizada",
        VacationTransactionType.Reversal => "Reintegro",
        VacationTransactionType.Adjustment => "Ajuste autorizado",
        _ => "—"
    };

    public static string Hours(decimal hours) => hours == 1 ? "1 hora" : $"{hours:0.##} horas";
    public static string Days(decimal days) => days == 1 ? "1 día" : $"{days:0.##} días";
}
