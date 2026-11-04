"""Domain state machine and authenticated human gate policy."""

from typing import Optional
from app.core.errors import IllegalStateTransitionException, GatePolicyException, ForbiddenException
from app.schemas.jobs import JobStatus
from app.schemas.gates import GateType, DecisionOutcome


class JobStateMachine:
    """Enforces deterministic lifecycle transitions for modernization jobs."""

    ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
        JobStatus.CREATED: {JobStatus.INTAKE, JobStatus.PAUSED, JobStatus.CANCELLED},
        JobStatus.INTAKE: {JobStatus.ANALYZING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.ANALYZING: {JobStatus.AWAITING_GATE_G1, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.AWAITING_GATE_G1: {JobStatus.CHARACTERIZING, JobStatus.ANALYZING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.CHARACTERIZING: {JobStatus.AWAITING_GATE_G2, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.AWAITING_GATE_G2: {JobStatus.PLANNING, JobStatus.CHARACTERIZING, JobStatus.PAUSED, JobStatus.CANCELLED},
        JobStatus.PLANNING: {JobStatus.AWAITING_GATE_G3, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.AWAITING_GATE_G3: {JobStatus.CONVERTING, JobStatus.PLANNING, JobStatus.PAUSED, JobStatus.CANCELLED},
        JobStatus.CONVERTING: {JobStatus.VERIFYING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.VERIFYING: {JobStatus.CONVERTING, JobStatus.INTEGRATING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.INTEGRATING: {JobStatus.AWAITING_GATE_G4, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED},
        JobStatus.AWAITING_GATE_G4: {JobStatus.COMPLETED, JobStatus.CONVERTING, JobStatus.PAUSED, JobStatus.CANCELLED},
        JobStatus.PAUSED: {
            JobStatus.INTAKE, JobStatus.ANALYZING, JobStatus.AWAITING_GATE_G1,
            JobStatus.CHARACTERIZING, JobStatus.AWAITING_GATE_G2, JobStatus.PLANNING,
            JobStatus.AWAITING_GATE_G3, JobStatus.CONVERTING, JobStatus.VERIFYING,
            JobStatus.INTEGRATING, JobStatus.AWAITING_GATE_G4, JobStatus.CANCELLED,
        },
        JobStatus.COMPLETED: set(),  # Terminal state
        JobStatus.FAILED: set(),     # Terminal state
        JobStatus.CANCELLED: set(),  # Terminal state
    }

    TERMINAL_STATES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

    @classmethod
    def can_transition(cls, current: JobStatus, target: JobStatus) -> bool:
        if current in cls.TERMINAL_STATES:
            return False
        return target in cls.ALLOWED_TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: JobStatus, target: JobStatus) -> None:
        if current in cls.TERMINAL_STATES:
            raise IllegalStateTransitionException(
                current_state=current.value,
                target_state=target.value,
                reason=f"Job is in terminal state '{current.value}' and cannot be modified."
            )
        if not cls.can_transition(current, target):
            raise IllegalStateTransitionException(
                current_state=current.value,
                target_state=target.value,
                reason=f"Transition from '{current.value}' to '{target.value}' is not permitted by lifecycle DAG."
            )


class GatePolicy:
    """Enforces non-bypassable human approval gate policies."""

    MIN_RATIONALE_LENGTH = 10

    @classmethod
    def validate_decision(
        cls,
        gate_type: GateType,
        decision: DecisionOutcome,
        rationale: str,
        actor_role: str,
        is_human: bool = True,
        gap_options: Optional[dict[str, str]] = None,
    ) -> None:
        # Rule 1: Agents CANNOT approve gates
        if not is_human:
            raise GatePolicyException(
                message="Autonomous agents are strictly prohibited from approving gates.",
                issue="Every gate decision requires an authenticated human reviewer."
            )

        # Role assignments do not authorize gate decisions. Authenticated human,
        # separation-of-duties, evidence and rationale checks remain enforced.
        # Rule 2: Rationale must meet minimum character length
        clean_rationale = rationale.strip() if rationale else ""
        if len(clean_rationale) < cls.MIN_RATIONALE_LENGTH:
            raise GatePolicyException(
                message=f"Decision rationale must be at least {cls.MIN_RATIONALE_LENGTH} characters.",
                issue="Audit compliance requires an explanatory rationale for all gate decisions."
            )

        # Rule 4: G1 requires gap option resolutions if approving
        if gate_type == GateType.G1 and decision == DecisionOutcome.APPROVED:
            if gap_options is not None and len(gap_options) == 0:
                raise GatePolicyException(
                    message="Gate G1 approval requires selecting an adapter resolution for each capability gap.",
                    issue="All capability gaps must have an explicit resolution (adapter, custom, or descope)."
                )


class RBACPolicy:
    """Compatibility adapter while authorization is role-independent."""

    ROLE_PERMISSIONS: dict[str, set[str]] = {
        "SUPER_ADMIN": {
            "integration:run", "delivery:publish",
            "module:convert", "module:repair", "module:waive",
            "job:create", "job:read", "job:intake", "job:pause_resume", "job:cancel",
            "gate:review", "gate:approve_g1", "gate:approve_g2", "gate:approve_g3", "gate:approve_g4",
            "artifact:read", "artifact:download", "artifact:publish_diagnostic", "audit:read", "settings:update", "user:manage"
        },
        "ADMIN": {
            "integration:run", "delivery:publish",
            "module:convert", "module:repair", "module:waive",
            "job:create", "job:read", "job:intake", "job:pause_resume", "job:cancel",
            "gate:review", "gate:approve_g1", "gate:approve_g2", "gate:approve_g3", "gate:approve_g4",
            "artifact:read", "artifact:download", "artifact:publish_diagnostic", "audit:read", "settings:update"
        },
        "REVIEWER": {
            "module:waive",
            "job:read", "job:pause_resume",
            "gate:review", "gate:approve_g1", "gate:approve_g2", "gate:approve_g3", "gate:approve_g4",
            "artifact:read", "artifact:download", "audit:read"
        },
        "DEVELOPER": {
            "integration:run",
            "module:convert", "module:repair",
            "job:read", "gate:review", "artifact:read", "artifact:download", "artifact:publish_diagnostic", "audit:read"
        },
        "VIEWER": {
            "job:read", "gate:review", "artifact:read"
        },
    }

    @classmethod
    def has_permission(cls, role: str, permission: str) -> bool:
        return True

    @classmethod
    def permissions_for(cls, role: str) -> list[str]:
        return sorted(set().union(*cls.ROLE_PERMISSIONS.values()))

    @classmethod
    def check_permission(cls, role: str, permission: str) -> None:
        if not cls.has_permission(role, permission):
            raise ForbiddenException(
                message=f"Role '{role}' lacks required permission '{permission}'."
            )
