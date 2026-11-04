"""Phase 5A Characterization & Gate G2 domain contracts."""

from app.characterization.contracts.enums import (
    CharacterizationStage,
    CoverageDimension,
    ExecutionStatus,
    FindingClassification,
    G2Decision,
    ScenarioStatus,
    ScenarioType,
)
from app.characterization.contracts.test_inventory import DiscoveredTestRecord, TestInventory
from app.characterization.contracts.workflows import (
    EntryPointDefinition,
    WorkflowDefinition,
    WorkflowInventory,
)
from app.characterization.contracts.scenarios import (
    ExecutionResult,
    ScenarioCatalog,
    ScenarioDefinition,
)
from app.characterization.contracts.observations import (
    ExecutionObservation,
    SideEffectInventory,
    StateChange,
)
from app.characterization.contracts.behavior import (
    BehaviorRule,
    BehaviorSpecification,
    StateTransition,
)
from app.characterization.contracts.coverage import CoverageMetric, CoverageReport
from app.characterization.contracts.uncertainty import UncertaintyRecord, UncertaintyReport
from app.characterization.contracts.approval import (
    G2ApprovalDecisionRecord,
    GateG2CompletionRecord,
    GateG2Request,
)
from app.characterization.contracts.suite import (
    CharacterizationContext,
    CharacterizationRequest,
    CharacterizationSuite,
)

__all__ = [
    "CharacterizationStage",
    "CoverageDimension",
    "ExecutionStatus",
    "FindingClassification",
    "G2Decision",
    "ScenarioStatus",
    "ScenarioType",
    "DiscoveredTestRecord",
    "TestInventory",
    "EntryPointDefinition",
    "WorkflowDefinition",
    "WorkflowInventory",
    "ScenarioDefinition",
    "ScenarioCatalog",
    "ExecutionResult",
    "StateChange",
    "SideEffectInventory",
    "ExecutionObservation",
    "StateTransition",
    "BehaviorRule",
    "BehaviorSpecification",
    "CoverageMetric",
    "CoverageReport",
    "UncertaintyRecord",
    "UncertaintyReport",
    "GateG2Request",
    "G2ApprovalDecisionRecord",
    "GateG2CompletionRecord",
    "CharacterizationContext",
    "CharacterizationRequest",
    "CharacterizationSuite",
]

