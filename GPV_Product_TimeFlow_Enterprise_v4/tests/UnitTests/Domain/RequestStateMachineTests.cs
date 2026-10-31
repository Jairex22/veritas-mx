using GPV.ProductTimeFlow.Domain;
using GPV.ProductTimeFlow.Shared;

namespace GPV.ProductTimeFlow.UnitTests.Domain;

public class RequestStateMachineTests
{
    public static TheoryData<RequestStatus, WorkflowAction, RequestStatus> ValidTransitions => new()
    {
        { RequestStatus.Draft, WorkflowAction.Submit, RequestStatus.Submitted },
        { RequestStatus.ReturnedForCorrection, WorkflowAction.Submit, RequestStatus.Submitted },
        { RequestStatus.Submitted, WorkflowAction.RouteToSupervisor, RequestStatus.PendingSupervisor },
        { RequestStatus.PendingSupervisor, WorkflowAction.SupervisorApprove, RequestStatus.SupervisorApproved },
        { RequestStatus.PendingSupervisor, WorkflowAction.SupervisorReject, RequestStatus.SupervisorRejected },
        { RequestStatus.PendingSupervisor, WorkflowAction.SupervisorReturn, RequestStatus.ReturnedForCorrection },
        { RequestStatus.SupervisorApproved, WorkflowAction.RouteToManager, RequestStatus.PendingManager },
        { RequestStatus.PendingManager, WorkflowAction.ManagerApprove, RequestStatus.ManagerApproved },
        { RequestStatus.PendingManager, WorkflowAction.ManagerReject, RequestStatus.ManagerRejected },
        { RequestStatus.PendingManager, WorkflowAction.ManagerReturn, RequestStatus.ReturnedForCorrection },
        { RequestStatus.ManagerApproved, WorkflowAction.RouteToAdministrative, RequestStatus.PendingAdministrativeRegistration },
        { RequestStatus.PendingAdministrativeRegistration, WorkflowAction.AdministrativeObserve, RequestStatus.AdministrativeObserved },
        { RequestStatus.AdministrativeObserved, WorkflowAction.AdministrativeObserve, RequestStatus.AdministrativeObserved },
        { RequestStatus.PendingAdministrativeRegistration, WorkflowAction.AdministrativeRegister, RequestStatus.AdministrativeRegistered },
        { RequestStatus.AdministrativeObserved, WorkflowAction.AdministrativeRegister, RequestStatus.AdministrativeRegistered },
        { RequestStatus.AdministrativeRegistered, WorkflowAction.Complete, RequestStatus.Completed },
        { RequestStatus.Draft, WorkflowAction.Cancel, RequestStatus.Cancelled },
        { RequestStatus.PendingSupervisor, WorkflowAction.Cancel, RequestStatus.Cancelled },
        { RequestStatus.ReturnedForCorrection, WorkflowAction.Cancel, RequestStatus.Cancelled },
        { RequestStatus.PendingManager, WorkflowAction.Cancel, RequestStatus.Cancelled },
    };

    [Theory]
    [MemberData(nameof(ValidTransitions))]
    public void Every_valid_transition_is_applied(RequestStatus from, WorkflowAction action, RequestStatus to)
    {
        Assert.True(RequestStateMachine.CanApply(from, action));
        Assert.Equal(to, RequestStateMachine.GetTarget(from, action));

        var request = new Request { Status = from };
        var now = new DateTime(2026, 3, 10, 12, 0, 0, DateTimeKind.Utc);
        Assert.Equal(to, request.Apply(action, now));
        Assert.Equal(to, request.Status);
        Assert.Equal(now, request.StatusChangedAtUtc);
        Assert.Equal(RequestStateMachine.IsTerminal(to) ? now : null, request.ClosedAtUtc);
    }

    [Fact]
    public void Transition_table_matches_the_expected_set_exactly()
    {
        var expected = ValidTransitions.Select(r => ((RequestStatus)r[0], (WorkflowAction)r[1], (RequestStatus)r[2])).ToHashSet();
        var actual = RequestStateMachine.Transitions.Select(t => (t.From, t.Action, t.To)).ToHashSet();
        Assert.Equal(expected.Count, RequestStateMachine.Transitions.Count);
        Assert.True(expected.SetEquals(actual));
    }

    [Theory]
    [InlineData(RequestStatus.Draft, WorkflowAction.SupervisorApprove)]
    [InlineData(RequestStatus.Draft, WorkflowAction.ManagerApprove)]
    [InlineData(RequestStatus.Draft, WorkflowAction.AdministrativeRegister)]
    [InlineData(RequestStatus.PendingSupervisor, WorkflowAction.ManagerApprove)]
    [InlineData(RequestStatus.PendingSupervisor, WorkflowAction.AdministrativeRegister)]
    [InlineData(RequestStatus.PendingSupervisor, WorkflowAction.Submit)]
    [InlineData(RequestStatus.PendingManager, WorkflowAction.SupervisorApprove)]
    [InlineData(RequestStatus.PendingManager, WorkflowAction.Complete)]
    [InlineData(RequestStatus.Completed, WorkflowAction.Cancel)]
    [InlineData(RequestStatus.Completed, WorkflowAction.Submit)]
    [InlineData(RequestStatus.ManagerRejected, WorkflowAction.Submit)]
    [InlineData(RequestStatus.SupervisorRejected, WorkflowAction.Submit)]
    [InlineData(RequestStatus.Cancelled, WorkflowAction.Submit)]
    [InlineData(RequestStatus.Cancelled, WorkflowAction.Cancel)]
    [InlineData(RequestStatus.ManagerApproved, WorkflowAction.Cancel)]
    [InlineData(RequestStatus.PendingAdministrativeRegistration, WorkflowAction.Cancel)]
    [InlineData(RequestStatus.PendingAdministrativeRegistration, WorkflowAction.Complete)]
    [InlineData(RequestStatus.AdministrativeRegistered, WorkflowAction.AdministrativeObserve)]
    [InlineData(RequestStatus.Submitted, WorkflowAction.SupervisorApprove)]
    public void Invalid_transitions_throw(RequestStatus from, WorkflowAction action)
    {
        Assert.False(RequestStateMachine.CanApply(from, action));
        var ex = Assert.Throws<InvalidTransitionException>(() => RequestStateMachine.Get(from, action));
        Assert.Equal(from, ex.From);
        Assert.Equal(action, ex.Action);

        var request = new Request { Status = from };
        Assert.Throws<InvalidTransitionException>(() => request.Apply(action, DateTime.UtcNow));
        Assert.Equal(from, request.Status); // el estado no cambia
    }

    [Fact]
    public void AdministrativeReceive_is_not_a_state_transition()
    {
        foreach (var s in Enum.GetValues<RequestStatus>())
            Assert.False(RequestStateMachine.CanApply(s, WorkflowAction.AdministrativeReceive));
        Assert.Throws<DomainException>(() => RequestStateMachine.AdministrativeWorkflowAction(AdministrativeAction.Receive));
    }

    [Theory]
    [InlineData(RequestStatus.SupervisorRejected)]
    [InlineData(RequestStatus.ManagerRejected)]
    [InlineData(RequestStatus.Completed)]
    [InlineData(RequestStatus.Cancelled)]
    public void Terminal_states_have_no_outgoing_transitions(RequestStatus status)
    {
        Assert.True(RequestStateMachine.IsTerminal(status));
        Assert.Empty(RequestStateMachine.AvailableActions(status));
    }

    [Fact]
    public void Non_terminal_states_are_not_terminal()
    {
        var terminal = new[] { RequestStatus.SupervisorRejected, RequestStatus.ManagerRejected, RequestStatus.Completed, RequestStatus.Cancelled };
        foreach (var s in Enum.GetValues<RequestStatus>().Except(terminal))
            Assert.False(RequestStateMachine.IsTerminal(s));
    }

    [Fact]
    public void Filter_one_cannot_be_skipped()
    {
        // Ninguna acción lleva de Submitted/PendingSupervisor/Draft/ReturnedForCorrection directo a PendingManager o etapas posteriores.
        var later = new[] { RequestStatus.PendingManager, RequestStatus.ManagerApproved, RequestStatus.PendingAdministrativeRegistration,
            RequestStatus.AdministrativeRegistered, RequestStatus.Completed };
        foreach (var from in new[] { RequestStatus.Draft, RequestStatus.Submitted, RequestStatus.PendingSupervisor, RequestStatus.ReturnedForCorrection })
            Assert.DoesNotContain(RequestStateMachine.Transitions, t => t.From == from && later.Contains(t.To));

        // El único camino a PendingManager es SupervisorApproved --RouteToManager-->.
        var intoManager = Assert.Single(RequestStateMachine.Transitions, t => t.To == RequestStatus.PendingManager);
        Assert.Equal(RequestStatus.SupervisorApproved, intoManager.From);
        Assert.Equal(WorkflowAction.RouteToManager, intoManager.Action);
        Assert.Equal(TransitionActor.System, intoManager.Actor);

        // Y a SupervisorApproved solo se llega con la aprobación de la jefa asignada.
        var intoSupApproved = Assert.Single(RequestStateMachine.Transitions, t => t.To == RequestStatus.SupervisorApproved);
        Assert.Equal((RequestStatus.PendingSupervisor, WorkflowAction.SupervisorApprove, TransitionActor.AssignedSupervisor),
            (intoSupApproved.From, intoSupApproved.Action, intoSupApproved.Actor));

        // Simulación: un empleado que intenta saltar el filtro 1.
        var r = new Request { Status = RequestStatus.Draft };
        r.Apply(WorkflowAction.Submit, DateTime.UtcNow);
        Assert.Throws<InvalidTransitionException>(() => r.Apply(WorkflowAction.RouteToManager, DateTime.UtcNow));
        r.Apply(WorkflowAction.RouteToSupervisor, DateTime.UtcNow);
        Assert.Throws<InvalidTransitionException>(() => r.Apply(WorkflowAction.RouteToManager, DateTime.UtcNow));
        Assert.Throws<InvalidTransitionException>(() => r.Apply(WorkflowAction.ManagerApprove, DateTime.UtcNow));
        Assert.Equal(RequestStatus.PendingSupervisor, r.Status);
    }

    [Fact]
    public void Automatic_follow_ups()
    {
        Assert.Equal(WorkflowAction.RouteToSupervisor, RequestStateMachine.AutomaticFollowUp(RequestStatus.Submitted));
        Assert.Equal(WorkflowAction.RouteToManager, RequestStateMachine.AutomaticFollowUp(RequestStatus.SupervisorApproved));
        Assert.Equal(WorkflowAction.RouteToAdministrative, RequestStateMachine.AutomaticFollowUp(RequestStatus.ManagerApproved));
        Assert.Null(RequestStateMachine.AutomaticFollowUp(RequestStatus.PendingSupervisor));
    }

    [Theory]
    [InlineData(ApprovalStepType.DirectSupervisor, ApprovalDecisionType.Approve, WorkflowAction.SupervisorApprove)]
    [InlineData(ApprovalStepType.DirectSupervisor, ApprovalDecisionType.Reject, WorkflowAction.SupervisorReject)]
    [InlineData(ApprovalStepType.DirectSupervisor, ApprovalDecisionType.Return, WorkflowAction.SupervisorReturn)]
    [InlineData(ApprovalStepType.SeniorManager, ApprovalDecisionType.Approve, WorkflowAction.ManagerApprove)]
    [InlineData(ApprovalStepType.SeniorManager, ApprovalDecisionType.Reject, WorkflowAction.ManagerReject)]
    [InlineData(ApprovalStepType.SeniorManager, ApprovalDecisionType.Return, WorkflowAction.ManagerReturn)]
    public void DecisionAction_maps_step_and_decision(ApprovalStepType step, ApprovalDecisionType decision, WorkflowAction expected)
    {
        Assert.Equal(expected, RequestStateMachine.DecisionAction(step, decision));
    }

    [Fact]
    public void AdministrativeRegistration_step_cannot_take_managerial_decisions()
    {
        Assert.Throws<DomainException>(() => RequestStateMachine.DecisionAction(ApprovalStepType.AdministrativeRegistration, ApprovalDecisionType.Approve));
    }
}
