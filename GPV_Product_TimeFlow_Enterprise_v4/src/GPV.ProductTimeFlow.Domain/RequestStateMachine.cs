using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.Domain;

public sealed class InvalidTransitionException(RequestStatus from, WorkflowAction action)
    : DomainException($"La acción «{Labels.Action(action)}» no es válida cuando la solicitud está «{Labels.Status(from)}».")
{
    public RequestStatus From { get; } = from;
    public WorkflowAction Action { get; } = action;
}

public class DomainException(string message) : Exception(message);

/// <summary>Quién puede ejecutar una acción (la identidad concreta se valida en Application).</summary>
public enum TransitionActor
{
    Requester,
    AssignedSupervisor,
    AssignedManager,
    AdministrativeRegistrar,
    System
}

public sealed record Transition(RequestStatus From, WorkflowAction Action, RequestStatus To, TransitionActor Actor);

/// <summary>
/// Máquina de estados formal del flujo EMPLEADO → JEFA DIRECTA → JEFE SUPERIOR → REGISTRO ADMINISTRATIVO.
/// Es la única fuente de verdad de transiciones válidas. Cualquier combinación no listada es inválida.
/// </summary>
public static class RequestStateMachine
{
    private static readonly Transition[] Table =
    [
        // Envío / reenvío
        new(RequestStatus.Draft, WorkflowAction.Submit, RequestStatus.Submitted, TransitionActor.Requester),
        new(RequestStatus.ReturnedForCorrection, WorkflowAction.Submit, RequestStatus.Submitted, TransitionActor.Requester),
        new(RequestStatus.Submitted, WorkflowAction.RouteToSupervisor, RequestStatus.PendingSupervisor, TransitionActor.System),

        // Filtro 1 · Jefa directa
        new(RequestStatus.PendingSupervisor, WorkflowAction.SupervisorApprove, RequestStatus.SupervisorApproved, TransitionActor.AssignedSupervisor),
        new(RequestStatus.PendingSupervisor, WorkflowAction.SupervisorReject, RequestStatus.SupervisorRejected, TransitionActor.AssignedSupervisor),
        new(RequestStatus.PendingSupervisor, WorkflowAction.SupervisorReturn, RequestStatus.ReturnedForCorrection, TransitionActor.AssignedSupervisor),
        new(RequestStatus.SupervisorApproved, WorkflowAction.RouteToManager, RequestStatus.PendingManager, TransitionActor.System),

        // Filtro 2 · Jefe superior (palabra final gerencial)
        new(RequestStatus.PendingManager, WorkflowAction.ManagerApprove, RequestStatus.ManagerApproved, TransitionActor.AssignedManager),
        new(RequestStatus.PendingManager, WorkflowAction.ManagerReject, RequestStatus.ManagerRejected, TransitionActor.AssignedManager),
        new(RequestStatus.PendingManager, WorkflowAction.ManagerReturn, RequestStatus.ReturnedForCorrection, TransitionActor.AssignedManager),
        new(RequestStatus.ManagerApproved, WorkflowAction.RouteToAdministrative, RequestStatus.PendingAdministrativeRegistration, TransitionActor.System),

        // Filtro 3 · Registro administrativo (no es una tercera aprobación gerencial)
        new(RequestStatus.PendingAdministrativeRegistration, WorkflowAction.AdministrativeObserve, RequestStatus.AdministrativeObserved, TransitionActor.AdministrativeRegistrar),
        new(RequestStatus.AdministrativeObserved, WorkflowAction.AdministrativeObserve, RequestStatus.AdministrativeObserved, TransitionActor.AdministrativeRegistrar),
        new(RequestStatus.PendingAdministrativeRegistration, WorkflowAction.AdministrativeRegister, RequestStatus.AdministrativeRegistered, TransitionActor.AdministrativeRegistrar),
        new(RequestStatus.AdministrativeObserved, WorkflowAction.AdministrativeRegister, RequestStatus.AdministrativeRegistered, TransitionActor.AdministrativeRegistrar),
        new(RequestStatus.AdministrativeRegistered, WorkflowAction.Complete, RequestStatus.Completed, TransitionActor.AdministrativeRegistrar),

        // Cancelación por el solicitante (solo antes de la decisión final gerencial)
        new(RequestStatus.Draft, WorkflowAction.Cancel, RequestStatus.Cancelled, TransitionActor.Requester),
        new(RequestStatus.PendingSupervisor, WorkflowAction.Cancel, RequestStatus.Cancelled, TransitionActor.Requester),
        new(RequestStatus.ReturnedForCorrection, WorkflowAction.Cancel, RequestStatus.Cancelled, TransitionActor.Requester),
        new(RequestStatus.PendingManager, WorkflowAction.Cancel, RequestStatus.Cancelled, TransitionActor.Requester),
    ];

    private static readonly Dictionary<(RequestStatus, WorkflowAction), Transition> Index =
        Table.ToDictionary(t => (t.From, t.Action));

    public static IReadOnlyList<Transition> Transitions => Table;

    public static bool CanApply(RequestStatus from, WorkflowAction action) => Index.ContainsKey((from, action));

    public static Transition Get(RequestStatus from, WorkflowAction action) =>
        Index.TryGetValue((from, action), out var t) ? t : throw new InvalidTransitionException(from, action);

    public static RequestStatus GetTarget(RequestStatus from, WorkflowAction action) => Get(from, action).To;

    public static IEnumerable<WorkflowAction> AvailableActions(RequestStatus from) =>
        Table.Where(t => t.From == from).Select(t => t.Action);

    public static bool IsTerminal(RequestStatus status) => status is RequestStatus.SupervisorRejected
        or RequestStatus.ManagerRejected or RequestStatus.Completed or RequestStatus.Cancelled;

    /// <summary>Transición automática del sistema que sigue a un estado intermedio, si existe.</summary>
    public static WorkflowAction? AutomaticFollowUp(RequestStatus status) => status switch
    {
        RequestStatus.Submitted => WorkflowAction.RouteToSupervisor,
        RequestStatus.SupervisorApproved => WorkflowAction.RouteToManager,
        RequestStatus.ManagerApproved => WorkflowAction.RouteToAdministrative,
        _ => null
    };

    public static WorkflowAction DecisionAction(ApprovalStepType step, ApprovalDecisionType decision) => (step, decision) switch
    {
        (ApprovalStepType.DirectSupervisor, ApprovalDecisionType.Approve) => WorkflowAction.SupervisorApprove,
        (ApprovalStepType.DirectSupervisor, ApprovalDecisionType.Reject) => WorkflowAction.SupervisorReject,
        (ApprovalStepType.DirectSupervisor, ApprovalDecisionType.Return) => WorkflowAction.SupervisorReturn,
        (ApprovalStepType.SeniorManager, ApprovalDecisionType.Approve) => WorkflowAction.ManagerApprove,
        (ApprovalStepType.SeniorManager, ApprovalDecisionType.Reject) => WorkflowAction.ManagerReject,
        (ApprovalStepType.SeniorManager, ApprovalDecisionType.Return) => WorkflowAction.ManagerReturn,
        _ => throw new DomainException("Decisión no válida para este filtro.")
    };

    public static WorkflowAction AdministrativeWorkflowAction(AdministrativeAction action) => action switch
    {
        AdministrativeAction.Observe => WorkflowAction.AdministrativeObserve,
        AdministrativeAction.Register => WorkflowAction.AdministrativeRegister,
        AdministrativeAction.Complete => WorkflowAction.Complete,
        _ => throw new DomainException("La recepción no cambia el estado de la solicitud.")
    };
}
