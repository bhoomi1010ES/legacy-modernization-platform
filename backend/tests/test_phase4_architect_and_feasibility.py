"""Tests for Phase 4 Architect Agent, TargetBlueprint Generation, Feasibility Assessment, and G1 Human Gap Decisions."""

import pytest
from app.services.architect_agent import ArchitectAgent
from app.services.feasibility_agent import FeasibilityAgent
from app.services.g1_decision_service import G1DecisionService
from app.schemas.phase4 import (
    LegacyModel,
    LegacyModule,
    PublicInterface,
    PersistenceEntity,
    TargetBlueprint,
    BlueprintStatus,
    FeasibilityReport,
    CapabilityClassification,
    G1DecisionType,
    G1DecisionRecord,
    ConfidenceLevel,
)


@pytest.fixture
def mock_legacy_model() -> LegacyModel:
    """Provides a realistic synthetic LegacyModel."""
    return LegacyModel(
        model_id="legacy_test_001",
        job_id="job_arch_001",
        snapshot_id="snap_arch_001",
        version=1,
        modules=[
            LegacyModule(
                module_id="mod_user",
                path="app/users",
                responsibility="User Identity and Profiles",
                language="Python",
                framework="Flask",
                entry_points=["routes.py"],
                public_interfaces=["iface_get_user", "iface_create_user"],
                dependencies=[],
                dependents=["mod_billing"],
                risk="MEDIUM",
                confidence=ConfidenceLevel.CONFIRMED,
                evidence_refs=["ev_mod_user"],
            ),
            LegacyModule(
                module_id="mod_billing",
                path="app/billing",
                responsibility="Payment and Subscription Processing",
                language="Python",
                framework="Flask",
                entry_points=["billing_routes.py"],
                public_interfaces=["iface_charge"],
                dependencies=["mod_user"],
                dependents=[],
                risk="HIGH",
                confidence=ConfidenceLevel.CONFIRMED,
                evidence_refs=["ev_mod_billing"],
            ),
        ],
        public_interfaces=[
            PublicInterface(
                interface_id="iface_get_user",
                interface_type="REST_ENDPOINT",
                name="GET /api/v1/users/{id}",
                location_path="app/users/routes.py",
                consumer_modules=["mod_billing"],
                evidence_refs=["ev_route_user"],
            ),
            PublicInterface(
                interface_id="iface_charge",
                interface_type="REST_ENDPOINT",
                name="POST /api/v1/billing/charge",
                location_path="app/billing/billing_routes.py",
                consumer_modules=[],
                evidence_refs=["ev_route_charge"],
            ),
        ],
        persistence_entities=[
            PersistenceEntity(
                entity_id="entity_users",
                name="users_table",
                entity_type="TABLE",
                database_engine="PostgreSQL",
                source_path="app/users/models.py",
                evidence_refs=["ev_table_users"],
            )
        ],
        content_hash="mock_hash_12345",
    )


class TestArchitectAndFeasibility:
    """Architect, Feasibility, and G1 human decision tests."""

    def test_architect_generates_target_blueprint(self, mock_legacy_model):
        """ArchitectAgent maps legacy model into valid versioned TargetBlueprint."""
        architect = ArchitectAgent()
        blueprint = architect.create_blueprint(
            legacy_model=mock_legacy_model,
            target_stack="FastAPI + PostgreSQL + SQLAlchemy Async",
            target_architecture="MODULAR_CLEAN_ARCHITECTURE",
            project_constraints=["Enforce token budget", "Use Alembic migrations"],
        )

        assert blueprint.blueprint_id.startswith("bp_")
        assert blueprint.version == 1
        assert blueprint.status == BlueprintStatus.UNDER_REVIEW
        assert len(blueprint.components) >= 2

        # Invariant 2: Every TargetBlueprint component maps to legacy capability or requirement
        for comp in blueprint.components:
            assert len(comp.mapped_legacy_modules) > 0 or "foundation" in comp.name.lower() or "shared" in comp.name.lower()

        # Interface preservation check
        assert len(blueprint.interfaces) >= 2
        user_iface = next((i for i in blueprint.interfaces if i.preserved_legacy_interface_id == "iface_get_user"), None)
        assert user_iface is not None
        assert user_iface.name == "GET /api/v1/users/{id}"

        # Blueprint hash must be deterministic
        assert len(blueprint.content_hash) == 64

    def test_feasibility_agent_evaluates_capabilities_and_tools(self, mock_legacy_model):
        """FeasibilityAgent categorizes capabilities into classifications and evaluates tools."""
        architect = ArchitectAgent()
        blueprint = architect.create_blueprint(
            legacy_model=mock_legacy_model,
            target_stack="FastAPI + PostgreSQL",
            target_architecture="MODULAR_CLEAN_ARCHITECTURE",
        )

        feasibility_agent = FeasibilityAgent()
        report = feasibility_agent.evaluate_feasibility(
            legacy_model=mock_legacy_model,
            target_blueprint=blueprint,
        )

        assert report.report_id.startswith("feas_")
        assert report.version == 1
        assert report.blueprint_version == blueprint.version
        assert len(report.capabilities) >= 3

        # Invariant 3: Every feasibility capability has a classification
        classifications = {c.classification for c in report.capabilities}
        assert CapabilityClassification.SUPPORTED in classifications
        for cap in report.capabilities:
            assert cap.classification in [
                CapabilityClassification.SUPPORTED,
                CapabilityClassification.SUBSTITUTE,
                CapabilityClassification.CUSTOM_BUILD,
                CapabilityClassification.UNSUPPORTED,
                CapabilityClassification.UNKNOWN,
            ]
            assert 0.0 <= cap.confidence <= 1.0

        # Tool readiness checks
        assert len(report.tool_readiness) >= 3
        tools = [tr.tool for tr in report.tool_readiness]
        assert "pytest" in tools
        assert "git" in tools

        # Feasibility score range check
        assert 0.0 <= report.overall_feasibility_score <= 1.0

    def test_g1_decision_service_routing(self, mock_legacy_model):
        """G1DecisionService handles all human gap decisions and creates immutable records."""
        architect = ArchitectAgent()
        blueprint = architect.create_blueprint(
            legacy_model=mock_legacy_model,
            target_stack="FastAPI + PostgreSQL",
            target_architecture="MODULAR_CLEAN_ARCHITECTURE",
        )
        feasibility_agent = FeasibilityAgent()
        report = feasibility_agent.evaluate_feasibility(
            legacy_model=mock_legacy_model,
            target_blueprint=blueprint,
        )

        g1_service = G1DecisionService()

        # Test decision: ACCEPT_SUBSTITUTE
        record_sub = G1DecisionRecord(
            decision_id="g1_dec_001",
            job_id="job_arch_001",
            capability_id=report.capabilities[0].capability_id,
            decision=G1DecisionType.ACCEPT_SUBSTITUTE,
            reason="Approved modern FastAPI dependency injection substitution",
            actor="lead_architect@enterprise.org",
            previous_feasibility_version=report.version,
        )

        outcome_sub = g1_service.apply_decision(
            blueprint=blueprint,
            feasibility_report=report,
            decision_record=record_sub,
        )
        assert outcome_sub["status"] == "APPLIED"
        assert outcome_sub["resulting_blueprint_version"] == 1

        # Test decision: REVISE_BLUEPRINT -> creates a new blueprint revision
        record_revise = G1DecisionRecord(
            decision_id="g1_dec_002",
            job_id="job_arch_001",
            capability_id=None,
            decision=G1DecisionType.REVISE_BLUEPRINT,
            reason="Revise blueprint to include Redis caching layer",
            actor="lead_architect@enterprise.org",
            previous_feasibility_version=report.version,
        )

        outcome_revise = g1_service.apply_decision(
            blueprint=blueprint,
            feasibility_report=report,
            decision_record=record_revise,
        )
        assert outcome_revise["status"] == "REVISION_REQUIRED"
        assert outcome_revise["resulting_blueprint_version"] == 2
        assert outcome_revise["rerun_triggered"] is True

        # Test decision: CANCEL
        record_cancel = G1DecisionRecord(
            decision_id="g1_dec_003",
            job_id="job_arch_001",
            decision=G1DecisionType.CANCEL,
            reason="User decided not to proceed with modernization",
            actor="lead_architect@enterprise.org",
            previous_feasibility_version=report.version,
        )
        outcome_cancel = g1_service.apply_decision(
            blueprint=blueprint,
            feasibility_report=report,
            decision_record=record_cancel,
        )
        assert outcome_cancel["status"] == "CANCELLED"
