"""Comprehensive Unit and Integration Test Suite for Phase 5A Characterization Engine and Gate G2."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.characterization.behavior.behavior_analyzer import BehaviorAnalyzer
from app.characterization.contracts.approval import GateG2Request
from app.characterization.contracts.behavior import BehaviorRule, BehaviorSpecification, StateTransition
from app.characterization.contracts.enums import (
    CharacterizationStage,
    CoverageDimension,
    ExecutionStatus,
    FindingClassification,
    G2Decision,
    ScenarioStatus,
    ScenarioType,
)
from app.characterization.contracts.observations import ExecutionObservation, SideEffectInventory, StateChange
from app.characterization.contracts.scenarios import ExecutionResult, ScenarioCatalog, ScenarioDefinition
from app.characterization.contracts.suite import CharacterizationRequest, CharacterizationSuite
from app.characterization.contracts.test_inventory import DiscoveredTestRecord, TestInventory
from app.characterization.contracts.uncertainty import UncertaintyReport
from app.characterization.contracts.workflows import EntryPointDefinition, WorkflowDefinition, WorkflowInventory
from app.characterization.coordinator import CharacterizationCoordinator
from app.characterization.coverage.coverage_calculator import CoverageCalculator
from app.characterization.discovery.test_discovery import UniversalTestDiscoveryEngine
from app.characterization.discovery.workflow_discovery import UniversalWorkflowDiscoveryEngine
from app.characterization.execution.sandbox import IsolatedExecutionSandbox
from app.characterization.gate_g2 import GateG2Manager
from app.characterization.models import (
    CharacterizationEventModel,
    CharacterizationExecutionModel,
    CharacterizationScenarioModel,
    CharacterizationSuiteModel,
    GateG2ApprovalModel,
)
from app.characterization.observation.filesystem_diff import FilesystemDiffer
from app.characterization.observation.normalizer import ObservationNormalizer
from app.characterization.observation.recorder import ObservationRecorder
from app.characterization.persistence.repository import CharacterizationRepository
from app.characterization.scenarios.scenario_designer import MultidimensionalScenarioDesigner
from app.characterization.suite_aggregator import SuiteAggregator
from app.core.storage import StorageAdapter
from app.models import Base
from app.models.job import Job
from app.models.user import User
from app.services.artifact_service import artifact_service


class MemoryStorage(StorageAdapter):
    def __init__(self):
        self.objects = {}

    async def put_object(self, key, data, media_type="application/json"):
        self.objects[key] = data
        return self.compute_sha256(data), len(data)

    async def get_object(self, key):
        return self.objects[key]

    async def object_exists(self, key):
        return key in self.objects

    async def delete_object(self, key):
        return self.objects.pop(key, None) is not None


async def _get_or_create_admin(db) -> User:
    from sqlalchemy import select
    user = await db.scalar(
        select(User).where(User.email == "char_auditor@example.com").limit(1)
    )
    if not user:
        user = User(
            user_id=uuid.uuid4(),
            email="char_auditor@example.com",
            password_hash="argon2id$mocked",
            role="SUPER_ADMIN",
            full_name="Char Auditor",
            status="ACTIVE",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


# =====================================================================
# Stage 1: Universal Test Discovery Tests
# =====================================================================
def test_universal_test_discovery():
    engine = UniversalTestDiscoveryEngine()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        test_py = root / "tests" / "test_auth.py"
        test_py.parent.mkdir(parents=True, exist_ok=True)
        test_py.write_text("def test_login_success():\n    pass\ndef test_invalid_creds():\n    pass\n")

        spec_js = root / "src" / "order.spec.js"
        spec_js.parent.mkdir(parents=True, exist_ok=True)
        spec_js.write_text("describe('Order', () => {\n  it('creates order', () => {});\n});\n")

        inv = engine.discover(root)
        assert inv.total_test_files == 2
        assert inv.total_test_cases >= 3
        assert len(inv.discovered_tests) == 2


def test_test_discovery_empty_or_missing():
    engine = UniversalTestDiscoveryEngine()
    inv = engine.discover(Path("/nonexistent/path/for/rebase/test"))
    assert inv.total_test_files == 0
    assert inv.total_test_cases == 0


# =====================================================================
# Stage 2: Universal Workflow & Route Discovery Tests
# =====================================================================
def test_universal_workflow_discovery():
    engine = UniversalWorkflowDiscoveryEngine()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        app_file = root / "routes.py"
        app_file.write_text(
            "@app.route('/api/login', methods=['POST'])\ndef login(): pass\n"
            "@router.get('/api/users')\ndef list_users(): pass\n"
            "@app.delete('/api/payment/checkout')\ndef checkout(): pass\n"
        )
        html_file = root / "templates" / "form.html"
        html_file.parent.mkdir(parents=True, exist_ok=True)
        html_file.write_text('<form action="/api/contact" method="POST"><input name="msg"/></form>')

        inv = engine.discover(root)
        assert inv.total_workflows >= 3
        assert inv.critical_workflows_count >= 2
        assert "login" in inv.domains_discovered or "api" in inv.domains_discovered


# =====================================================================
# Stage 3: Multidimensional Scenario Designer Tests
# =====================================================================
def test_scenario_designer_4_quadrants():
    designer = MultidimensionalScenarioDesigner()
    wf = WorkflowDefinition(
        workflow_id="wf_auth_login",
        name="User Authentication",
        domain="auth",
        description="Handles user login and credentials",
        is_critical=True,
        entrypoints=[
            EntryPointDefinition(
                entrypoint_id="ep_login",
                entrypoint_type="REST_ENDPOINT",
                path="/api/login",
                method="POST",
                source_file="routes.py",
            )
        ],
    )
    inv = WorkflowInventory(
        total_workflows=1,
        critical_workflows_count=1,
        workflows=[wf],
        domains_discovered=["auth"],
    )

    catalog = designer.design(inv, max_scenarios=10)
    assert catalog.total_scenarios == 4

    types_generated = {s.scenario_type for s in catalog.scenarios}
    assert types_generated == {
        ScenarioType.POSITIVE,
        ScenarioType.BOUNDARY,
        ScenarioType.INVALID_INPUT,
        ScenarioType.ERROR_PATH,
    }
    for s in catalog.scenarios:
        assert s.scenario_id.startswith("scen_")


# =====================================================================
# Stage 4: FilesystemDiffer & ObservationNormalizer Tests
# =====================================================================
def test_filesystem_differ():
    differ = FilesystemDiffer()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        file1 = root / "file1.txt"
        file1.write_text("initial")

        pre_snap = differ.capture_snapshot(root)
        assert "file1.txt" in pre_snap

        file1.write_text("updated content")
        file2 = root / "file2.txt"
        file2.write_text("created")

        post_snap = differ.capture_snapshot(root)
        created, modified, deleted, changes = differ.diff(pre_snap, post_snap)

        assert "file2.txt" in created
        assert "file1.txt" in modified
        assert len(changes) == 2


def test_observation_normalizer():
    norm = ObservationNormalizer()
    raw = {
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "created_at": "2026-11-04T12:00:00Z",
        "nested": {"msg": "Order 123e4567-e89b-12d3-a456-426614174000 processed"},
    }
    normalized = norm.normalize_data(raw)
    assert normalized["user_id"] == "<UUID_1>"
    assert normalized["created_at"] == "<TIMESTAMP_1>"
    assert "<UUID_1>" in normalized["nested"]["msg"]


# =====================================================================
# Stage 5: IsolatedExecutionSandbox Tests (Security & Sanitization)
# =====================================================================
def test_sandbox_security_blacklist():
    sandbox = IsolatedExecutionSandbox()
    assert sandbox.is_prohibited_command("python -m unittest discover") is False
    assert sandbox.is_prohibited_command("pytest tests/") is False

    # Prohibited commands must trigger detection
    assert sandbox.is_prohibited_command("rm -rf /") is True
    assert sandbox.is_prohibited_command("mkfs.ext4 /dev/sda1") is True


def test_sandbox_environment_sanitization(monkeypatch):
    sandbox = IsolatedExecutionSandbox()
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super_secret_aws_key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://root:pwd@prod:5432/db")
    monkeypatch.setenv("SAFE_TEST_VAR", "safe_val")

    clean = sandbox.sanitize_environment()
    assert "AWS_SECRET_ACCESS_KEY" not in clean
    assert "DATABASE_URL" not in clean
    assert clean.get("SAFE_TEST_VAR") == "safe_val"


# =====================================================================
# Stage 6: BehaviorAnalyzer & Contradiction Detection Tests
# =====================================================================
def test_behavior_analyzer_contradiction_detection():
    analyzer = BehaviorAnalyzer()
    wf_id = "wf_checkout"

    scen1 = ScenarioDefinition(
        scenario_id="scen_1",
        workflow_id=wf_id,
        scenario_type=ScenarioType.POSITIVE,
        name="Checkout 1",
        objective="Nominal checkout",
        inputs={"amount": 100},
    )
    scen2 = ScenarioDefinition(
        scenario_id="scen_2",
        workflow_id=wf_id,
        scenario_type=ScenarioType.POSITIVE,
        name="Checkout 2",
        objective="Nominal checkout repeat",
        inputs={"amount": 100},
    )
    catalog = ScenarioCatalog(total_scenarios=2, scenarios=[scen1, scen2])

    res1 = ExecutionResult(
        scenario_id="scen_1",
        workflow_id=wf_id,
        status=ScenarioStatus.EXECUTED,
        passed=True,
        exit_code=0,
        duration_ms=10.0,
    )
    res2 = ExecutionResult(
        scenario_id="scen_2",
        workflow_id=wf_id,
        status=ScenarioStatus.EXECUTED,
        passed=False,
        exit_code=1,
        duration_ms=10.0,
    )

    obs1 = ExecutionObservation(
        observation_id="obs_1",
        scenario_id="scen_1",
        workflow_id=wf_id,
        execution_mode="HOST_PROCESS_FALLBACK",
        exit_code=0,
        duration_ms=10.0,
        side_effects=SideEffectInventory(),
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    obs2 = ExecutionObservation(
        observation_id="obs_2",
        scenario_id="scen_2",
        workflow_id=wf_id,
        execution_mode="HOST_PROCESS_FALLBACK",
        exit_code=1,
        duration_ms=10.0,
        side_effects=SideEffectInventory(),
        captured_at=datetime.now(timezone.utc).isoformat(),
    )

    spec = analyzer.analyze(catalog, [res1, res2], [obs1, obs2])
    assert spec.contradictions_count >= 1
    assert "Contradiction in workflow wf_checkout" in spec.contradictions[0]


# =====================================================================
# Stage 7: 9-Dimension Coverage Calculator Tests
# =====================================================================
def test_coverage_calculator_9_dimensions():
    calc = CoverageCalculator()
    wf = WorkflowDefinition(
        workflow_id="wf_1",
        name="Cart Checkout",
        domain="cart",
        description="Checkout workflow",
        is_critical=True,
        entrypoints=[
            EntryPointDefinition(
                entrypoint_id="ep_1",
                entrypoint_type="REST_ENDPOINT",
                path="/checkout",
                method="POST",
                source_file="cart.py",
            )
        ],
    )
    inv = WorkflowInventory(total_workflows=1, critical_workflows_count=1, workflows=[wf])
    catalog = ScenarioCatalog(
        total_scenarios=2,
        scenarios=[
            ScenarioDefinition(
                scenario_id="scen_pos",
                workflow_id="wf_1",
                scenario_type=ScenarioType.POSITIVE,
                name="Valid Checkout",
                objective="Test checkout success",
                inputs={"cart_id": "1"},
            ),
            ScenarioDefinition(
                scenario_id="scen_err",
                workflow_id="wf_1",
                scenario_type=ScenarioType.ERROR_PATH,
                name="Failed Checkout",
                objective="Test checkout rejection",
                inputs={"cart_id": "0"},
            ),
        ],
    )
    exec_results = [
        ExecutionResult(
            scenario_id="scen_pos",
            workflow_id="wf_1",
            status=ScenarioStatus.EXECUTED,
            passed=True,
            exit_code=0,
            duration_ms=10.0,
        ),
        ExecutionResult(
            scenario_id="scen_err",
            workflow_id="wf_1",
            status=ScenarioStatus.EXECUTED,
            passed=True,
            exit_code=0,
            duration_ms=12.0,
        ),
    ]
    obs = [
        ExecutionObservation(
            observation_id="obs_1",
            scenario_id="scen_pos",
            workflow_id="wf_1",
            execution_mode="HOST_PROCESS_FALLBACK",
            exit_code=0,
            duration_ms=10.0,
            state_changes=[
                StateChange(change_type="FILE_MODIFIED", target="order.db")
            ],
            side_effects=SideEffectInventory(storage_mutations=1),
            captured_at=datetime.now(timezone.utc).isoformat(),
        ),
        ExecutionObservation(
            observation_id="obs_2",
            scenario_id="scen_err",
            workflow_id="wf_1",
            execution_mode="HOST_PROCESS_FALLBACK",
            exit_code=1,
            duration_ms=12.0,
            side_effects=SideEffectInventory(),
            captured_at=datetime.now(timezone.utc).isoformat(),
        ),
    ]
    behavior_spec = BehaviorSpecification(
        total_rules=1,
        contradictions_count=0,
        rules=[
            BehaviorRule(
                rule_id="rule_1",
                workflow_id="wf_1",
                condition="Valid cart",
                consequence="Order created",
                classification=FindingClassification.OBSERVED_FACT,
            )
        ],
        state_transitions=[
            StateTransition(
                transition_id="trans_1",
                workflow_id="wf_1",
                from_state="CART",
                to_state="ORDER_CREATED",
                trigger_action="checkout",
                observed_mutations=["order.db"],
            )
        ],
    )

    report = calc.calculate(inv, catalog, exec_results, obs, behavior_spec, g2_threshold_pct=50.0)
    assert len(report.dimensions) == 9
    assert report.dimensions[CoverageDimension.WORKFLOW_COVERAGE.value].percentage == 100.0
    assert report.dimensions[CoverageDimension.CRITICAL_BEHAVIOR_COVERAGE.value].percentage == 100.0
    assert report.aggregate_percentage > 50.0
    assert report.meets_g2_threshold is True


# =====================================================================
# Stage 8: Suite Aggregator & Deterministic Content Hashing Tests
# =====================================================================
def test_suite_aggregator_hash_invariance():
    aggregator = SuiteAggregator()
    wf = WorkflowDefinition(
        workflow_id="wf_a",
        name="WFA",
        domain="test",
        description="Test workflow",
    )
    inv = WorkflowInventory(total_workflows=1, workflows=[wf])
    catalog = ScenarioCatalog(
        total_scenarios=1,
        scenarios=[
            ScenarioDefinition(
                scenario_id="scen_a",
                workflow_id="wf_a",
                scenario_type=ScenarioType.POSITIVE,
                name="Test A",
                objective="Objective A",
                inputs={},
            )
        ],
    )
    results = [
        ExecutionResult(
            scenario_id="scen_a",
            workflow_id="wf_a",
            status=ScenarioStatus.EXECUTED,
            passed=True,
            exit_code=0,
            duration_ms=5.0,
        )
    ]
    obs = [
        ExecutionObservation(
            observation_id="obs_a",
            scenario_id="scen_a",
            workflow_id="wf_a",
            execution_mode="HOST_PROCESS_FALLBACK",
            exit_code=0,
            duration_ms=5.0,
            side_effects=SideEffectInventory(),
            captured_at="2026-11-04T12:00:00Z",
        )
    ]
    spec = BehaviorSpecification(total_rules=0, contradictions_count=0)
    calc = CoverageCalculator()
    cov = calc.calculate(inv, catalog, results, obs, spec)
    uncertainty = UncertaintyReport(total_uncertainties=0)

    job_id = str(uuid.uuid4())
    suite1 = aggregator.aggregate(
        suite_id="suite_1",
        job_id=job_id,
        version=1,
        test_inventory=TestInventory(),
        workflow_inventory=inv,
        scenario_catalog=catalog,
        execution_results=results,
        observations=obs,
        behavior_spec=spec,
        coverage_report=cov,
        uncertainty_report=uncertainty,
        created_at="2026-11-04T12:00:00Z",
        is_partial=False,
    )
    suite2 = aggregator.aggregate(
        suite_id="suite_1",
        job_id=job_id,
        version=1,
        test_inventory=TestInventory(),
        workflow_inventory=inv,
        scenario_catalog=catalog,
        execution_results=results,
        observations=obs,
        behavior_spec=spec,
        coverage_report=cov,
        uncertainty_report=uncertainty,
        created_at="2026-11-04T12:00:00Z",
        is_partial=False,
    )

    assert suite1.content_hash == suite2.content_hash
    assert len(suite1.content_hash) == 64


# =====================================================================
# Stage 9: Gate G2 Manager Readiness & Freeze Tests
# =====================================================================
def test_gate_g2_manager_readiness_and_freeze():
    g2 = GateG2Manager()
    aggregator = SuiteAggregator()

    wf = WorkflowDefinition(
        workflow_id="wf_1",
        name="WF",
        domain="test",
        description="Test workflow",
        is_critical=True,
    )
    inv = WorkflowInventory(total_workflows=1, critical_workflows_count=1, workflows=[wf])
    catalog = ScenarioCatalog(
        total_scenarios=1,
        scenarios=[
            ScenarioDefinition(
                scenario_id="scen_1",
                workflow_id="wf_1",
                scenario_type=ScenarioType.POSITIVE,
                name="Scen 1",
                objective="Objective 1",
                inputs={},
            )
        ],
    )
    results = [
        ExecutionResult(
            scenario_id="scen_1",
            workflow_id="wf_1",
            status=ScenarioStatus.EXECUTED,
            passed=True,
            exit_code=0,
            duration_ms=5.0,
        )
    ]
    obs = [
        ExecutionObservation(
            observation_id="obs_1",
            scenario_id="scen_1",
            workflow_id="wf_1",
            execution_mode="HOST_PROCESS_FALLBACK",
            exit_code=0,
            duration_ms=5.0,
            side_effects=SideEffectInventory(),
            captured_at="2026-11-04T12:00:00Z",
        )
    ]
    spec = BehaviorSpecification(total_rules=0, contradictions_count=0)
    calc = CoverageCalculator()
    cov = calc.calculate(inv, catalog, results, obs, spec, g2_threshold_pct=10.0)
    uncertainty = UncertaintyReport(total_uncertainties=0)

    suite = aggregator.aggregate(
        suite_id="suite_1",
        job_id=str(uuid.uuid4()),
        version=1,
        test_inventory=TestInventory(),
        workflow_inventory=inv,
        scenario_catalog=catalog,
        execution_results=results,
        observations=obs,
        behavior_spec=spec,
        coverage_report=cov,
        uncertainty_report=uncertainty,
        created_at="2026-11-04T12:00:00Z",
        is_partial=False,
    )

    readiness = g2.evaluate_gate_readiness(suite, coverage_threshold_pct=10.0)
    assert readiness["ready"] is True
    assert len(readiness["blocking_reasons"]) == 0

    req = GateG2Request(
        decision=G2Decision.APPROVE,
        rationale="Sign-off on characterization baseline.",
        conditions=[],
    )
    decision_rec, updated_suite = g2.process_g2_decision(suite, req, decided_by="reviewer_1")
    assert decision_rec.decision == G2Decision.APPROVE
    assert updated_suite.is_frozen is True
    assert decision_rec.suite_content_hash == suite.content_hash


# =====================================================================
# End-to-End Characterization Coordinator Test
# =====================================================================
def test_characterization_coordinator_e2e(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(artifact_service, "publish_artifact", AsyncMock())

    job_id = uuid.uuid4()
    repo = CharacterizationRepository(db=None)
    events_received = []
    coordinator = CharacterizationCoordinator(
        event_callback=lambda evt: events_received.append(evt),
        repo=repo,
    )

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "test_app.py").write_text("def test_sample():\n    assert 1 == 1\n")
    (repo_dir / "app.py").write_text(
        "@app.route('/health', methods=['GET'])\ndef health():\n    return 'OK'\n"
        "@app.route('/login', methods=['POST'])\ndef login():\n    return 'LOGIN_OK'\n"
    )

    ti = coordinator.test_engine.discover(repo_dir)
    assert ti.total_test_files == 1

    wi = coordinator.workflow_engine.discover(repo_dir)
    assert wi.total_workflows >= 2

    cat = coordinator.designer.design_catalog(wi)
    assert cat.total_scenarios >= 8

    # Stage 4: Execution
    results = []
    obs_list = []
    with tempfile.TemporaryDirectory() as sbox:
        sbox_path = Path(sbox)
        for scen in cat.scenarios:
            r, mode = coordinator.sandbox.execute_scenario(scen, repo_dir, sbox_path)
            results.append(r)
            obs = coordinator.recorder.record(
                execution_result=r,
                execution_mode=mode,
                created_files=[],
                modified_files=[],
                deleted_files=[],
                state_changes=[],
                reproducibility="DETERMINISTIC",
            )
            obs_list.append(obs)
    assert len(results) == len(cat.scenarios)
    assert len(obs_list) == len(cat.scenarios)

    # Stage 5: Behavior Analysis
    spec = coordinator.analyzer.analyze(cat, results, obs_list)
    assert spec is not None

    # Stage 6: Coverage Calculation
    cov = coordinator.coverage_calc.calculate(wi, cat, results, obs_list, spec, g2_threshold_pct=10.0)
    assert cov.aggregate_percentage >= 10.0

    # Stage 7: Uncertainty
    unc = UncertaintyReport(total_uncertainties=0)

    # Stage 8: Aggregation
    suite = coordinator.aggregator.aggregate(
        suite_id="suite_test_1",
        job_id=str(job_id),
        version=1,
        test_inventory=ti,
        workflow_inventory=wi,
        scenario_catalog=cat,
        execution_results=results,
        observations=obs_list,
        behavior_spec=spec,
        coverage_report=cov,
        uncertainty_report=unc,
        created_at="2026-11-04T12:00:00Z",
    )
    assert suite is not None
    assert suite.version == 1
    assert len(suite.content_hash) == 64

    # Stage 9: Gate G2 Readiness
    readiness = coordinator.g2_manager.evaluate_gate_readiness(suite, coverage_threshold_pct=10.0)
    assert readiness["ready"] is True

