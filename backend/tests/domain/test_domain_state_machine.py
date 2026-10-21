"""Domain state machine and approval gate policy tests."""

import pytest
from app.core.errors import IllegalStateTransitionException, GatePolicyException, ForbiddenException
from app.domain.state_machine import JobStateMachine, GatePolicy
from app.schemas.jobs import JobStatus
from app.schemas.gates import GateType, DecisionOutcome


def test_valid_sequential_transitions():
    """Verifies that legal DAG transitions pass validation."""
    valid_path = [
        (JobStatus.CREATED, JobStatus.INTAKE),
        (JobStatus.INTAKE, JobStatus.ANALYZING),
        (JobStatus.ANALYZING, JobStatus.AWAITING_GATE_G1),
        (JobStatus.AWAITING_GATE_G1, JobStatus.CHARACTERIZING),
        (JobStatus.CHARACTERIZING, JobStatus.AWAITING_GATE_G2),
        (JobStatus.AWAITING_GATE_G2, JobStatus.PLANNING),
        (JobStatus.PLANNING, JobStatus.AWAITING_GATE_G3),
        (JobStatus.AWAITING_GATE_G3, JobStatus.CONVERTING),
        (JobStatus.CONVERTING, JobStatus.VERIFYING),
        (JobStatus.VERIFYING, JobStatus.INTEGRATING),
        (JobStatus.INTEGRATING, JobStatus.AWAITING_GATE_G4),
        (JobStatus.AWAITING_GATE_G4, JobStatus.COMPLETED),
    ]
    for current, target in valid_path:
        assert JobStateMachine.can_transition(current, target) is True
        # Should not raise exception:
        JobStateMachine.validate_transition(current, target)


def test_illegal_stage_skipping_rejected():
    """Verifies that skipping mandatory analysis, tests, or gates is strictly rejected."""
    illegal_transitions = [
        (JobStatus.CREATED, JobStatus.CONVERTING),
        (JobStatus.CREATED, JobStatus.COMPLETED),
        (JobStatus.ANALYZING, JobStatus.CONVERTING),
        (JobStatus.AWAITING_GATE_G1, JobStatus.COMPLETED),
        (JobStatus.AWAITING_GATE_G2, JobStatus.CONVERTING),
        (JobStatus.PLANNING, JobStatus.INTEGRATING),
    ]
    for current, target in illegal_transitions:
        assert JobStateMachine.can_transition(current, target) is False
        with pytest.raises(IllegalStateTransitionException) as exc_info:
            JobStateMachine.validate_transition(current, target)
        assert exc_info.value.code == "ILLEGAL_STATE_TRANSITION"


def test_terminal_states_cannot_transition():
    """Verifies that COMPLETED, FAILED, and CANCELLED jobs reject any subsequent transition."""
    terminal_states = [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
    for terminal in terminal_states:
        for any_target in [JobStatus.CREATED, JobStatus.CONVERTING, JobStatus.INTAKE]:
            assert JobStateMachine.can_transition(terminal, any_target) is False
            with pytest.raises(IllegalStateTransitionException):
                JobStateMachine.validate_transition(terminal, any_target)


def test_cancellation_permitted_from_non_terminal_states():
    """Verifies that cancellation is supported from non-terminal states."""
    active_states = [
        JobStatus.CREATED,
        JobStatus.INTAKE,
        JobStatus.ANALYZING,
        JobStatus.AWAITING_GATE_G1,
        JobStatus.CHARACTERIZING,
        JobStatus.CONVERTING,
        JobStatus.VERIFYING,
        JobStatus.PAUSED,
    ]
    for state in active_states:
        assert JobStateMachine.can_transition(state, JobStatus.CANCELLED) is True
        JobStateMachine.validate_transition(state, JobStatus.CANCELLED)


def test_gate_policy_valid_human_approval():
    """Verifies that an authorized human reviewer with sufficient rationale passes G1–G4 checks."""
    # Should not raise:
    GatePolicy.validate_decision(
        gate_type=GateType.G3,
        decision=DecisionOutcome.APPROVED,
        rationale="All 18 modules reviewed with clean wave dependency boundaries.",
        actor_role="REVIEWER",
        is_human=True,
    )


def test_gate_policy_short_rationale_rejected():
    """Verifies that gate approvals with insufficient rationale (<10 chars) are rejected."""
    with pytest.raises(GatePolicyException) as exc_info:
        GatePolicy.validate_decision(
            gate_type=GateType.G1,
            decision=DecisionOutcome.APPROVED,
            rationale="Looks ok",  # 8 chars (< 10)
            actor_role="ADMIN",
            is_human=True,
        )
    assert "at least 10 characters" in exc_info.value.message


def test_gate_policy_agent_self_approval_rejected():
    """Verifies that autonomous agents are strictly blocked from approving gates."""
    with pytest.raises(GatePolicyException) as exc_info:
        GatePolicy.validate_decision(
            gate_type=GateType.G2,
            decision=DecisionOutcome.APPROVED,
            rationale="Test suite verified automatically by Characterizer agent.",
            actor_role="ADMIN",
            is_human=False,  # Agent attempt
        )
    assert "prohibited from approving gates" in exc_info.value.message


def test_gate_policy_unauthorized_role_rejected():
    """Verifies that DEVELOPER or VIEWER roles cannot submit gate decisions."""
    with pytest.raises(ForbiddenException):
        GatePolicy.validate_decision(
            gate_type=GateType.G4,
            decision=DecisionOutcome.APPROVED,
            rationale="Approved by junior developer without delivery authority.",
            actor_role="DEVELOPER",
            is_human=True,
        )
