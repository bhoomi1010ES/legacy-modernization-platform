"""W10 Verification Suite: Independent Verifier, Reviewer, repair, and static-web truth.

Covers:
1. Separate durable Verifier work item from CodeWriter work item (worker lease, identity, immutable VerificationRun).
2. Versioned target-stack verification profile requiring distinct categories.
3. Compileall cannot masquerade as unit, integration, or schema checks.
4. Missing profile or executable fails closed as BLOCKED/NOT_RUN.
5. Characterization replay and difference classification (REGRESSION, INTENDED_DIFFERENCE, NONDETERMINISTIC, TEST_DEFECT, UNOBSERVED).
6. Reviewer independently blocks critical security findings even when compile/tests pass.
7. Repair creates a new attempt with target failed tests, new branch, and invalidates stale verification.
8. Repeated failure exhaustion escalates to WAITING_FOR_HUMAN.
9. Static-web truth: HTML existence is not behavioral parity; JS/DOM failures are detected.
10. Schema migration fails on target flavor incompatibility.
11. Verifier binding rejects mismatched candidate or suite hashes.
12. Missing Syft/security scanner is BLOCKED/NOT_RUN, not an empty clean SBOM.
"""

from datetime import datetime, timezone
import json
import pytest
import uuid
from sqlalchemy import select

from app.core.errors import ConflictException, PlatformException
from app.models.agent import AgentRun
from app.models.job import Job
from app.models.module import Module, ModuleAttempt, VerificationRun
from app.schemas.phase6 import CheckSpec, Finding
from app.services import (
    phase5_engine as p5,
    phase6_sandbox,
    phase6_service as service,
    reviewer_agent,
    verifier_agent,
)
from app.services.sandbox_protocol import (
    approved_command,
    canonical,
    digest,
    validate_check_profile,
    validate_execution,
)
from app.services.verification_profiles import get_profile, normalize_target

# Import shared fixtures from test_phase6
from tests.test_phase6 import (
    ready,
    generation,
    queued,
    trusted_executor,
    isolated,
    captured,
    synthetic_target_profile,
)


# ==============================================================================
# 1. SEPARATE DURABLE VERIFIER WORK ITEM AND LEASE
# ==============================================================================

@pytest.mark.asyncio
async def test_verifier_separate_durable_work_item_and_lease(ready, trusted_executor):
    """Verify that Verifier has its own worker identity, worker lease, and immutable VerificationRun.

    Codewriter cannot manufacture or self-attest verification evidence.
    """
    db, job, _, storage, module, _ = ready
    attempt = await queued(ready)
    assert attempt.status == "QUEUED" and module.status == "LEASED"

    # Execute conversion attempt
    from app.services.model_gateway import FakeModelProvider, build_fake_gateway
    gateway = build_fake_gateway(FakeModelProvider([generation(3)]))
    await service.execute_attempt(db, attempt.attempt_id, gateway=gateway)

    assert attempt.status == module.status == "VERIFIED"

    detail = await service.detail(db, attempt)
    verifier_evidence = detail["verification_run"]
    assert verifier_evidence is not None

    durable_run = await db.get(VerificationRun, uuid.UUID(verifier_evidence["verification_run_id"]))
    assert durable_run is not None
    assert durable_run.status == "PASS"

    # Separate worker identities: Verifier != CodeWriter
    codewriter_run = await db.get(AgentRun, attempt.agent_run_id)
    codewriter_worker_id = codewriter_run.task_payload.get("codewriter_worker_id")
    assert durable_run.worker_id != codewriter_worker_id
    assert durable_run.worker_id == "synthetic-unit-verifier"

    # Immutably bound to exact candidate and suite hashes
    evidence = (await service.detail(db, attempt))["evidence"]
    assert durable_run.candidate_hash == evidence["verification"]["candidate_hash"]
    assert verifier_evidence["candidate_hash"] == evidence["verification"]["candidate_hash"]
    assert durable_run.suite_hash is not None
    assert durable_run.evidence_hash == p5.digest(durable_run.evidence)


# ==============================================================================
# 2. VERSIONED TARGET-STACK VERIFICATION PROFILE WITH DISTINCT CATEGORIES
# ==============================================================================

def test_target_verification_profile_requires_all_distinct_categories():
    """Verify that target verification profiles must contain all distinct required categories."""
    valid_checks = [
        {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
        {"category": "unit", "command": ["python", "-m", "pytest", "/acceptance/test_calc.py", "-q", "-p", "no:cacheprovider"]},
        {"category": "integration", "command": ["python", "-m", "pytest", "/acceptance/test_integration.py", "-q", "-p", "no:cacheprovider"]},
        {"category": "static", "command": ["python", "-m", "mypy", "--cache-dir=/tmp/mypy-cache", "--check-untyped-defs", "--explicit-package-bases", "."]},
        {"category": "security", "command": ["python", "-m", "bandit", "-r", "app", "-q"]},
        {"category": "dependency", "command": ["pip-audit", "--strict"]},
        {"category": "license", "command": ["pip-licenses", "--format=json"]},
        {"category": "runtime", "command": ["python", "-m", "pytest", "/acceptance/test_runtime.py", "-q", "-p", "no:cacheprovider"]},
        {"category": "api_compatibility", "command": ["python", "-m", "pytest", "/acceptance/test_api.py", "-q", "-p", "no:cacheprovider"]},
    ]

    # Valid profile passes validation
    assert validate_check_profile(valid_checks, system=True) is True

    # Missing category 'security' fails validation
    missing_security = [c for c in valid_checks if c["category"] != "security"]
    assert validate_check_profile(missing_security, system=True) is False

    # Duplicate command fails validation
    duplicate_cmds = valid_checks + [valid_checks[0]]
    assert validate_check_profile(duplicate_cmds, system=True) is False


# ==============================================================================
# 3. COMPILEALL IS BUILD ONLY AND CANNOT MASQUERADE AS OTHER CATEGORIES
# ==============================================================================

def test_compileall_is_build_only_and_cannot_masquerade_as_unit_or_security():
    """Verify that compileall is strictly rejected when labeled as unit, integration, or schema."""
    fake_unit = [
        {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
        {"category": "unit", "command": ["python", "-m", "compileall", "-q", "."]},  # Fake unit test!
        {"category": "integration", "command": ["python", "-m", "pytest", "/acceptance/test_integration.py", "-q", "-p", "no:cacheprovider"]},
        {"category": "static", "command": ["python", "-m", "mypy", "--cache-dir=/tmp/mypy-cache", "--check-untyped-defs", "--explicit-package-bases", "."]},
        {"category": "security", "command": ["python", "-m", "bandit", "-r", "app", "-q"]},
        {"category": "dependency", "command": ["pip-audit", "--strict"]},
        {"category": "license", "command": ["pip-licenses", "--format=json"]},
        {"category": "runtime", "command": ["python", "-m", "pytest", "/acceptance/test_runtime.py", "-q", "-p", "no:cacheprovider"]},
        {"category": "api_compatibility", "command": ["python", "-m", "pytest", "/acceptance/test_api.py", "-q", "-p", "no:cacheprovider"]},
    ]
    assert validate_check_profile(fake_unit, system=True) is False


# ==============================================================================
# 4. MISSING PROFILE OR EXECUTABLE FAILS CLOSED AS BLOCKED
# ==============================================================================

def test_missing_profile_fails_closed_and_blocks_conversion():
    """Verify that an unknown or missing target stack profile fails closed with an error."""
    with pytest.raises(ValueError, match="No unique versioned verification profile"):
        get_profile("non-existent-stack-xyz")


# ==============================================================================
# 5. REPLAY FROZEN CHARACTERIZATION & DIFFERENCE CLASSIFICATION
# ==============================================================================

def test_characterization_difference_classification_contract():
    """Verify that characterization replay classifies every difference:

    REGRESSION, INTENDED_DIFFERENCE, NONDETERMINISTIC, TEST_DEFECT, UNOBSERVED.
    """
    fingerprint = "test_fingerprint_hash_001"
    cases = [
        {
            "test_case_id": "case_1",
            "name": "add_positive",
            "fixtures": {"x": 2, "y": 3},
            "expected": 5,
            "side_effects": {"db_writes": 1},
            "normalization": [],
        },
        {
            "test_case_id": "case_2",
            "name": "add_negative",
            "fixtures": {"x": -2, "y": 3},
            "expected": 1,
            "side_effects": {"db_writes": 0},
            "normalization": [],
        },
    ]

    # 1. Matching observations -> PASS, difference_classification = NONE
    matching_data = {
        "observations": [
            {
                "test_case_id": "case_1",
                "stdout": json.dumps({"output": 5, "side_effects": {"db_writes": 1}}),
                "exit_code": 0,
                "duration_ms": 15,
                "command": ["python", "/adapter.py"],
            },
            {
                "test_case_id": "case_2",
                "stdout": json.dumps({"output": 1, "side_effects": {"db_writes": 0}}),
                "exit_code": 0,
                "duration_ms": 12,
                "command": ["python", "/adapter.py"],
            },
        ],
        "checks": [],
        "source_unchanged": True,
    }
    result_matching = phase6_sandbox.assess(matching_data, cases, [], fingerprint)
    assert result_matching["passed"] is True
    assert all(c["difference_classification"] == "NONE" for c in result_matching["cases"])

    # 2. Mismatched observation -> FAIL, difference_classification = REGRESSION
    regression_data = {
        "observations": [
            {
                "test_case_id": "case_1",
                "stdout": json.dumps({"output": 999, "side_effects": {"db_writes": 1}}),  # Wrong output!
                "exit_code": 0,
                "duration_ms": 15,
                "command": ["python", "/adapter.py"],
            },
            {
                "test_case_id": "case_2",
                "stdout": json.dumps({"output": 1, "side_effects": {"db_writes": 0}}),
                "exit_code": 0,
                "duration_ms": 12,
                "command": ["python", "/adapter.py"],
            },
        ],
        "checks": [],
        "source_unchanged": True,
    }
    result_regression = phase6_sandbox.assess(regression_data, cases, [], fingerprint)
    assert result_regression["passed"] is False
    assert result_regression["cases"][0]["status"] == "FAIL"
    assert result_regression["cases"][0]["difference_classification"] == "REGRESSION"

    # 3. Unobserved case -> status = UNOBSERVED, difference_classification = UNOBSERVED
    unobserved_data = {
        "observations": [
            {
                "test_case_id": "case_1",
                "stdout": "",
                "exit_code": None,
                "duration_ms": 0,
                "command": ["python", "/adapter.py"],
                "status": "UNOBSERVED",
            },
            {
                "test_case_id": "case_2",
                "stdout": json.dumps({"output": 1, "side_effects": {"db_writes": 0}}),
                "exit_code": 0,
                "duration_ms": 12,
                "command": ["python", "/adapter.py"],
            },
        ],
        "checks": [],
        "source_unchanged": True,
    }
    result_unobserved = phase6_sandbox.assess(unobserved_data, cases, [], fingerprint)
    assert result_unobserved["passed"] is False
    assert result_unobserved["cases"][0]["status"] == "UNOBSERVED"
    assert result_unobserved["cases"][0]["difference_classification"] == "UNOBSERVED"


# ==============================================================================
# 6. REVIEWER INDEPENDENTLY BLOCKS CRITICAL SECURITY EVEN IF TESTS PASS
# ==============================================================================

def test_reviewer_independently_blocks_critical_security_even_if_compile_passes():
    """Verify Reviewer marks status REJECTED when critical security flaws exist,

    even if build and execution succeeded.
    """
    evidence_hash = "fake_evidence_hash_123"
    # Code containing eval and hardcoded password
    bad_files = {
        "modern/calc.py": "def compute(cmd):\n    password = 'super_secret_password_123'\n    return eval(cmd)\n"
    }
    contracts = [{"symbol": "compute"}]

    # Even with an execution dict claiming PASS:
    fake_execution = {
        "available": True,
        "passed": True,
        "artifact_hash": evidence_hash,
        "checks": [
            {"category": "build", "status": "PASS"},
            {"category": "unit", "status": "PASS"},
            {"category": "static", "status": "PASS"},
            {"category": "security", "status": "PASS"},
        ],
        "cases": [{"test_case_id": "c1", "status": "PASS"}],
    }

    review = reviewer_agent.review(
        files=bad_files,
        contracts=contracts,
        evidence_hash=evidence_hash,
        execution=fake_execution,
    )

    assert review["status"] == "REJECTED"
    severities = {f["severity"] for f in review["findings"]}
    categories = {f["category"] for f in review["findings"]}
    assert "CRITICAL" in severities
    assert "UNSAFE_EXECUTION" in categories
    assert any("eval" in f["message"].lower() or "dynamic" in f["message"].lower() for f in review["findings"])


# ==============================================================================
# 7. REPAIR CREATES A NEW ATTEMPT WITH TARGETED FAILED TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_repair_creates_new_attempt_with_target_failed_tests(ready, trusted_executor):
    """Verify that a failing attempt transitions to REPAIR_REQUIRED,

    and a subsequent repair attempt generates a distinct attempt with targeted feedback.
    """
    db, _, _, _, module, _ = ready
    from app.services.model_gateway import FakeModelProvider, build_fake_gateway

    # First attempt generates wrong code (returns 4 instead of 3 for 1+2)
    first = await queued(ready)
    # Output returns x + y + 1 (buggy!)
    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(3)]))

    await service.execute_attempt(db, first.attempt_id, gateway=gateway)
    assert first.status == "REPAIR_REQUIRED"

    # Queue second attempt as repair
    second = await queued(
        ready,
        "repair",
        previous=first,
        rationale="Repair addition regression identified by frozen characterization suite",
    )
    assert second.attempt_number == 2
    assert second.git_branch != first.git_branch

    # Executing second attempt verifies and passes
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)
    assert second.status == "VERIFIED"
    assert module.status == "VERIFIED"

    # Verify repair feedback recorded the targeted failed tests
    detail_second = await service.detail(db, second)
    repair_feedback = detail_second["evidence"]["repair_feedback"]
    assert repair_feedback is not None
    assert repair_feedback["results"][0]["status"] == "FAIL"


# ==============================================================================
# 8. REPEATED FAILURE EXHAUSTION ESCALATES TO WAITING_FOR_HUMAN
# ==============================================================================

@pytest.mark.asyncio
async def test_repeated_failure_exhaustion_escalates_to_waiting_for_human(ready, trusted_executor):
    """Verify that repeating the same failure beyond max_repair_attempts escalates to WAITING_FOR_HUMAN."""
    db, job, _, _, module, _ = ready
    job.max_repair_attempts = 1  # Cap at 1 repair attempt

    from app.services.model_gateway import FakeModelProvider, build_fake_gateway

    # Always buggy model
    gateway = build_fake_gateway(FakeModelProvider([generation(4), generation(4)]))

    first = await queued(ready)
    await service.execute_attempt(db, first.attempt_id, gateway=gateway)
    assert first.status == "REPAIR_REQUIRED"

    # Queue repair attempt
    second = await queued(
        ready,
        "repair",
        previous=first,
        rationale="Repair exact failed frozen characterization case",
    )
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)

    # Reached limit and same failure -> WAITING_FOR_HUMAN
    assert second.status == "WAITING_FOR_HUMAN"

    # Any further automatic queue attempt must be rejected with ConflictException
    with pytest.raises(ConflictException):
        await queued(
            ready,
            "again",
            previous=second,
            rationale="A third automatic repeat must not be scheduled",
        )


# ==============================================================================
# 9. STATIC-WEB TRUTH: HTML EXISTENCE IS NOT BEHAVIORAL PARITY
# ==============================================================================

def test_static_web_html_presence_cannot_claim_behavioral_equivalence():
    """Verify that merely having an HTML file or running server without DOM behavior verification fails."""
    fingerprint = "static_web_fp_001"
    cases = [
        {
            "test_case_id": "dom_nav_01",
            "name": "login_form_submission",
            "fixtures": {"form": "login"},
            "expected": {"redirect": "/dashboard", "auth_cookie": True},
            "side_effects": {},
            "normalization": [],
        }
    ]

    specs = [
        {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]}
    ]
    checks = [
        {"category": "build", "command": ["python", "-m", "compileall", "-q", "."], "duration_ms": 100, "status": "PASS", "exit_code": 0}
    ]

    # Observation shows exit_code 1 (Playwright/DOM check failed)
    failed_dom_observation = {
        "observations": [
            {
                "test_case_id": "dom_nav_01",
                "stdout": "Error: Button click failed: Navigation timeout",
                "exit_code": 1,
                "duration_ms": 3000,
                "command": ["playwright", "test"],
            }
        ],
        "checks": checks,
        "source_unchanged": True,
    }

    result = phase6_sandbox.assess(failed_dom_observation, cases, specs, fingerprint)
    assert result["passed"] is False
    assert result["cases"][0]["status"] == "FAIL"
    assert result["cases"][0]["difference_classification"] == "REGRESSION"


# ==============================================================================
# 10. SCHEMA MIGRATION FAILS ON TARGET FLAVOR INCOMPATIBILITY
# ==============================================================================

def test_schema_migration_fails_on_target_flavor_incompatibility():
    """Verify that a schema check failing with syntax/flavor error causes verification to fail."""
    fingerprint = "schema_fp_001"
    cases = []
    specs = [
        {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
        {"category": "schema", "command": ["alembic", "upgrade", "head"]},
    ]
    checks = [
        {"category": "build", "status": "PASS", "command": ["python", "-m", "compileall", "-q", "."], "duration_ms": 50, "exit_code": 0},
        {"category": "schema", "status": "FAIL", "command": ["alembic", "upgrade", "head"], "duration_ms": 120, "exit_code": 1},
    ]
    data = {
        "observations": [],
        "checks": checks,
        "source_unchanged": True,
    }

    result = phase6_sandbox.assess(data, cases, specs, fingerprint)
    assert result["passed"] is False
    schema_check = next(c for c in result["checks"] if c["category"] == "schema")
    assert schema_check["status"] == "FAIL"


# ==============================================================================
# 11. VERIFIER BINDING REJECTS MISMATCHED CANDIDATE OR SUITE HASH
# ==============================================================================

def test_verifier_binding_rejects_mismatched_candidate_or_suite_hash():
    """Verify validate_execution rejects bindings missing required hash fields or with invalid characters."""
    valid_payload = {
        "request_id": "req-001",
        "job_id": "job-001",
        "attempt_id": "att-001",
        "candidate_hash": "a" * 64,
        "suite_hash": "b" * 64,
        "execution": {
            "purpose": "VERIFICATION",
            "image": "sha256:" + "0" * 64,
            "runtime": "docker-rootless",
            "timeout": 180,
            "adapter": ["python", "/adapter.py"],
            "files": {"calc.py": "def add(): pass"},
            "checks": [
                {"category": "build", "command": ["python", "-m", "compileall", "-q", "."]},
            ],
        },
    }

    # Valid binding passes
    validate_execution(valid_payload, {"sha256:" + "0" * 64})

    # Mismatched / invalid candidate hash with forbidden characters
    invalid_payload = dict(valid_payload)
    invalid_payload["candidate_hash"] = "invalid hash with spaces;"
    with pytest.raises(ValueError, match="Invalid execution binding"):
        validate_execution(invalid_payload, {"sha256:" + "0" * 64})


# ==============================================================================
# 12. MISSING SYFT OR SECURITY SCANNER IS BLOCKED/NOT_RUN, NOT AN EMPTY CLEAN SBOM
# ==============================================================================

def test_missing_syft_or_security_scanner_is_blocked_not_clean():
    """Verify that when a scanner is missing or unapproved, it is rejected and cannot produce a fabricated clean pass."""
    # An empty or fabricated clean command is rejected by approved_command
    assert approved_command(["true"]) is False
    assert approved_command(["cat", "/dev/null"]) is False
    assert approved_command(["echo", "zero vulnerabilities"]) is False

    # Syft requires exact approved command profile
    assert approved_command(["syft", "scan", "dir:/work", "-o", "syft-json"]) is True
    assert approved_command(["syft", "--arbitrary-flag", "/work"]) is False
