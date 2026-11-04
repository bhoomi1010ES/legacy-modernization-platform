"""Domain persistence models registry for Rebase Modernization Platform."""

from app.models.base import Base, GUID, TimestampMixin, utc_now
from app.models.role import Role
from app.models.user import User, UserSession
from app.models.job import Job, JobMembership
from app.models.module import Module, ModuleAttempt, ModuleDependency, VerificationRun
from app.models.agent import AgentRun
from app.models.artifact import Artifact, ArtifactDependency
from app.models.test_case import TestCase, TestResult
from app.models.gate import GateDecision
from app.models.audit import AuditEvent
from app.models.budget import BudgetUsage
from app.models.workflow import WorkflowCheckpoint, WorkflowGate, WorkflowOutbox
from app.models.worker import WorkerRegistry
from app.models.model_gateway import ModelGatewayBudget, ModelGatewayRequest
from app.models.phase4 import (
    RepositorySnapshotModel,
    RepositoryInventoryModel,
    AnalysisRunModel,
    AnalysisWorkerModel,
    LegacyModelRecord,
    AnalysisEvidenceRecord,
    AnalysisConflictRecord,
    TargetBlueprintModel,
    FeasibilityReportModel,
    FeasibilityCapabilityModel,
    FeasibilityDecisionModel,
    PlannerRunModel,
    PlannerOutputModel,
    ConversionPlanModel,
    ConversionPlanModuleModel,
    ConversionPlanTaskModel,
    ConversionPlanDependencyModel,
)
from app.models.characterization import (
    CharacterizationExecutionModel,
    CharacterizationSuiteModel,
    CharacterizationScenarioModel,
    CharacterizationEventModel,
    GateG2ApprovalModel,
)

__all__ = [
    "Base",
    "GUID",
    "TimestampMixin",
    "utc_now",
    "Role",
    "User",
    "UserSession",
    "Job",
    "JobMembership",
    "Module",
    "ModuleAttempt",
    "ModuleDependency",
    "VerificationRun",
    "AgentRun",
    "Artifact",
    "ArtifactDependency",
    "TestCase",
    "TestResult",
    "GateDecision",
    "AuditEvent",
    "BudgetUsage",
    "WorkflowCheckpoint",
    "WorkflowGate",
    "WorkflowOutbox",
    "WorkerRegistry",
    "ModelGatewayBudget",
    "ModelGatewayRequest",
    "RepositorySnapshotModel",
    "RepositoryInventoryModel",
    "AnalysisRunModel",
    "AnalysisWorkerModel",
    "LegacyModelRecord",
    "AnalysisEvidenceRecord",
    "AnalysisConflictRecord",
    "TargetBlueprintModel",
    "FeasibilityReportModel",
    "FeasibilityCapabilityModel",
    "FeasibilityDecisionModel",
    "PlannerRunModel",
    "PlannerOutputModel",
    "ConversionPlanModel",
    "ConversionPlanModuleModel",
    "ConversionPlanTaskModel",
    "ConversionPlanDependencyModel",
    "CharacterizationExecutionModel",
    "CharacterizationSuiteModel",
    "CharacterizationScenarioModel",
    "CharacterizationEventModel",
    "GateG2ApprovalModel",
]
