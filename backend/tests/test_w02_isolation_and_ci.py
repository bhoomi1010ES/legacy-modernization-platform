"""W02 Verification Suite: Isolated Reproducible Test Infrastructure, Isolation Guards & Two Model Lanes."""

import os
import secrets
import tempfile
from pathlib import Path
import pytest

from app.core.testing_infrastructure import (
    DisposableDatabaseManager,
    IsolationGuard,
    ProtectedResourceError,
    IsolationTokenError,
)
from app.services.model_gateway import (
    ModelGateway,
    ModelLane,
    ModelNotAllowedError,
    ModelGatewayError,
    RealModelBudgetTracker,
    TwoLaneModelRouter,
    build_fake_gateway,
    FakeModelProvider,
)
from tests.fixtures.fixture_loader import ReferenceFixtureLoader

# ==============================================================================
# 1. Isolation Guards & Production Resource Protection (TEST-04 Verification)
# ==============================================================================


@pytest.mark.unit
@pytest.mark.security_negative
def test_production_database_url_refusal():
    """Verify that test runner strictly refuses to execute against production 'rebase' database."""
    protected_urls = [
        "postgresql://postgres:postres123@localhost:5432/rebase",
        "postgresql+asyncpg://postgres:postres123@localhost:5432/rebase",
        "postgresql://user:pass@db.internal:5432/rebase",
        "postgresql://user:pass@db.internal:5432/rebase_prod",
        "postgresql://user:pass@db.internal:5432/rebase_db",
        "postgresql://user:pass@db.internal:5432/production",
        "postgresql://user:pass@db.internal:5432/staging",
    ]
    for url in protected_urls:
        with pytest.raises(ProtectedResourceError) as exc_info:
            IsolationGuard.verify_database_url(url)
        assert "TEST ISOLATION VIOLATION" in str(exc_info.value)
        assert "Refusing test execution against protected" in str(
            exc_info.value
        ) or "lacks required" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.security_negative
def test_unmarked_database_url_refusal():
    """Verify refusal when database name does not contain required test/disposable marker."""
    unmarked_urls = [
        "postgresql://localhost:5432/myapp",
        "postgresql://localhost:5432/customer_data",
        "postgresql://localhost:5432/analytics",
    ]
    for url in unmarked_urls:
        with pytest.raises(ProtectedResourceError) as exc_info:
            IsolationGuard.verify_database_url(url)
        assert "lacks required test/disposable markers" in str(exc_info.value)


@pytest.mark.unit
def test_valid_disposable_database_url_allowed():
    """Verify that correctly marked disposable test database names are permitted."""
    valid_urls = [
        "postgresql://localhost:5432/rebase_test_w01",
        "postgresql://localhost:5432/rebase_test_abc123",
        "postgresql+asyncpg://localhost:5432/rebase_disposable_999",
        "postgresql://localhost:5432/isolated_run_12",
    ]
    for url in valid_urls:
        db_name = IsolationGuard.verify_database_url(url)
        assert any(m in db_name for m in ("test", "disposable", "isolated"))


@pytest.mark.unit
@pytest.mark.security_negative
def test_isolation_token_enforcement(monkeypatch):
    """Verify that test execution strictly requires and checks TEST_ISOLATION_TOKEN."""
    expected_token = secrets.token_hex(16)
    monkeypatch.setenv("TEST_ISOLATION_TOKEN", expected_token)

    # Valid token passes
    db_name = IsolationGuard.verify_database_url(
        "postgresql://localhost:5432/rebase_test_unit",
        isolation_token=expected_token,
    )
    assert db_name == "rebase_test_unit"

    # Mismatched token fails
    with pytest.raises(IsolationTokenError) as exc_info:
        IsolationGuard.verify_database_url(
            "postgresql://localhost:5432/rebase_test_unit",
            isolation_token="invalid-token-xyz",
        )
    assert "Invalid TEST_ISOLATION_TOKEN" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.security_negative
def test_storage_path_isolation():
    """Verify that test storage rejects persistent paths and accepts temp directories."""
    # Forbidden path
    with pytest.raises(ProtectedResourceError):
        IsolationGuard.verify_storage_path(Path("artifacts/production/data"))

    # Allowed temporary path
    with tempfile.TemporaryDirectory() as tmp_dir:
        verified = IsolationGuard.verify_storage_path(Path(tmp_dir))
        assert verified.exists()


@pytest.mark.unit
@pytest.mark.security_negative
def test_git_remote_isolation():
    """Verify that external production git destinations are rejected in test mode."""
    forbidden_remotes = [
        "https://github.com/enterprise/production-repo.git",
        "git@github.com:enterprise/production-repo.git",
        "https://gitlab.com/rebase/legacy.git",
    ]
    for remote in forbidden_remotes:
        with pytest.raises(ProtectedResourceError):
            IsolationGuard.verify_git_remote(remote)

    allowed_remotes = [
        "https://localhost:8443/repo.git",
        "http://127.0.0.1:3000/fixture.git",
        "file:///tmp/fixture-repo",
        "backend/tests/fixtures/reference_repos/fastapi_source",
    ]
    for remote in allowed_remotes:
        assert IsolationGuard.verify_git_remote(remote) == remote


# ==============================================================================
# 2. Disposable PostgreSQL Lifecycle (Create -> Migrate -> Drop)
# ==============================================================================


@pytest.mark.db_integration
def test_disposable_postgres_lifecycle():
    """Verify automated creation, migration, and teardown of disposable database."""
    import psycopg2

    manager = DisposableDatabaseManager()
    db_name = manager.generate_database_name()

    # Step 1: Create disposable database
    created_name = manager.create_database(db_name)
    assert created_name == db_name
    assert db_name in manager.active_databases

    # Verify DB exists in PostgreSQL catalog
    conn = psycopg2.connect(manager.admin_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            assert (
                cur.fetchone() is not None
            ), f"Database {db_name} was not found in catalog"

        # Step 2: Run Alembic migrations on disposable DB
        backend_dir = Path(__file__).resolve().parent.parent
        manager.run_migrations(db_name, backend_dir=backend_dir)

        # Verify tables were created
        with psycopg2.connect(
            f"postgresql://postgres:postres123@localhost:5432/{db_name}"
        ) as test_conn:
            with test_conn.cursor() as test_cur:
                test_cur.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
                )
                table_count = test_cur.fetchone()[0]
                assert (
                    table_count >= 30
                ), f"Expected migrated tables >= 30, got {table_count}"

        # Step 3: Tear down disposable DB
        manager.drop_database(db_name)
        assert db_name not in manager.active_databases

        # Verify DB is gone from PostgreSQL catalog
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            assert (
                cur.fetchone() is None
            ), f"Database {db_name} was not dropped from catalog"
    finally:
        conn.close()


# ==============================================================================
# 3. Two Model Lanes: Deterministic Fake vs Budget-Capped Real Sandbox
# ==============================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deterministic_fake_model_lane():
    """Verify deterministic fake model lane returns reproducible output with acceptance notice."""
    gateway = build_fake_gateway()
    result = await gateway.complete(
        provider="fake",
        model="fake-model-v1",
        request={
            "prompt": "Convert legacy function",
            "task": {"task_id": "test-task-1"},
        },
    )

    assert result.response.action == "final"
    assert result.response.usage.cost_usd == 0.0

    meta = result.response.provider_metadata
    assert meta["model_lane"] == ModelLane.DETERMINISTIC_FAKE
    assert meta["acceptance_claim_valid"] is False
    assert "not eligible as real E2E acceptance evidence" in meta["audit_note"]


@pytest.mark.unit
@pytest.mark.security_negative
@pytest.mark.asyncio
async def test_real_model_lane_disabled_by_default(monkeypatch):
    """Verify that calling real model provider fails when REAL_MODEL_SANDBOX_ENABLED is False."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "REAL_MODEL_SANDBOX_ENABLED", False)

    gateway = ModelGateway(
        providers={"openai": FakeModelProvider()},
        allowlist={"openai": {"gpt-4o"}},
        timeout_seconds=5.0,
    )

    with pytest.raises(ModelNotAllowedError) as exc_info:
        await gateway.complete(
            provider="openai",
            model="gpt-4o",
            request={"prompt": "Real task"},
        )
    assert "Real model lane is disabled" in str(exc_info.value)
    assert "REAL_MODEL_SANDBOX_ENABLED=true" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_real_model_lane_budget_cap_enforcement(monkeypatch):
    """Verify that real model lane tracks spend and halts when budget ceiling is exceeded."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "REAL_MODEL_SANDBOX_ENABLED", True)
    monkeypatch.setattr(settings, "MAX_BUDGET_USD", 0.05)

    tracker = RealModelBudgetTracker.get_tracker()
    tracker.reset()

    # Create fake provider mimicking real provider with cost
    mock_real_provider = FakeModelProvider(
        responses=[
            {
                "action": "final",
                "output": {"content": "First response"},
                "usage": {"input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.03},
            },
            {
                "action": "final",
                "output": {"content": "Second response"},
                "usage": {"input_tokens": 1000, "output_tokens": 500, "cost_usd": 0.03},
            },
        ]
    )

    gateway = ModelGateway(
        providers={"openai": mock_real_provider},
        allowlist={"openai": {"gpt-4o"}},
        timeout_seconds=5.0,
    )

    # First call: within budget ($0.03 < $0.05)
    res1 = await gateway.complete(
        provider="openai", model="gpt-4o", request={"prompt": "Task 1"}
    )
    assert res1.response.provider_metadata["model_lane"] == ModelLane.BUDGET_CAPPED_REAL
    assert res1.response.provider_metadata["acceptance_claim_valid"] is True
    assert tracker.total_spent_usd == 0.03

    # Second call: within budget before start, but now cumulative spend is $0.06 >= $0.05
    res2 = await gateway.complete(
        provider="openai", model="gpt-4o", request={"prompt": "Task 2"}
    )
    assert tracker.total_spent_usd == 0.06

    # Third call: rejected immediately because cumulative spend ($0.06) >= ceiling ($0.05)
    with pytest.raises(ModelGatewayError) as exc_info:
        await gateway.complete(
            provider="openai", model="gpt-4o", request={"prompt": "Task 3"}
        )
    assert "Real model budget ceiling exceeded" in str(exc_info.value)

    tracker.reset()


# ==============================================================================
# 4. Committed Synthetic Reference Repositories
# ==============================================================================


@pytest.mark.unit
@pytest.mark.e2e_fixture
def test_synthetic_reference_fixtures_integrity():
    """Verify all 7 committed synthetic reference fixtures exist and load correctly."""
    # 1. FastAPI source
    fastapi = ReferenceFixtureLoader.load_fastapi_source()
    assert "FastAPI" in fastapi["main.py"]
    assert "/items" in fastapi["main.py"]
    assert "fastapi" in fastapi["requirements.txt"]

    # 2. Django target
    django = ReferenceFixtureLoader.load_django_target()
    assert "serializers.Serializer" in django["serializers.py"]
    assert "APIView" in django["views.py"]
    assert "djangorestframework" in django["requirements.txt"]

    # 3. Static web app
    static_app = ReferenceFixtureLoader.load_static_web_app()
    assert "<!DOCTYPE html>" in static_app["index.html"]
    assert "Modernization Dashboard" in static_app["index.html"]
    assert "font-family" in static_app["styles.css"]
    assert "addEventListener" in static_app["app.js"]

    # 4. SQL-backed service
    sql_svc = ReferenceFixtureLoader.load_sql_backed_service()
    assert "declarative_base" in sql_svc["models.py"]
    assert "Customer" in sql_svc["models.py"]

    # 5. Broken fixture (syntax error & missing import)
    broken = ReferenceFixtureLoader.load_broken_fixture()
    assert "def broken_function(:" in broken["syntax_error.py"]
    assert "non_existent_rebase_package" in broken["missing_import.py"]

    # 6. Slow worker fixture
    slow = ReferenceFixtureLoader.load_slow_worker_fixture()
    assert "execute_long_job" in slow["worker.py"]
    assert "time.sleep" in slow["worker.py"]

    # 7. Malicious security fixture
    malicious = ReferenceFixtureLoader.load_malicious_security_fixture()
    assert len(malicious["path_traversals"]) >= 3
    assert len(malicious["ssrf_targets"]) >= 3
    assert len(malicious["prompt_injections"]) >= 3
    assert any("/etc/shadow" in p for p in malicious["path_traversals"])
    assert any("169.254.169.254" in s for s in malicious["ssrf_targets"])


# ==============================================================================
# 5. Testing Infrastructure Robustness & Edge Cases
# ==============================================================================


@pytest.mark.unit
def test_empty_database_url_refusal():
    """Verify that empty or unparseable database URLs are rejected."""
    with pytest.raises(ProtectedResourceError) as exc_info:
        IsolationGuard.verify_database_url("")
    assert "Empty or unparseable" in str(exc_info.value)


@pytest.mark.unit
def test_invalid_database_name_pattern():
    """Verify that database names with injection characters are rejected."""
    manager = DisposableDatabaseManager()
    with pytest.raises(ValueError) as exc_info:
        manager.create_database("test_db; DROP TABLE users;--")
    assert "Invalid database name" in str(exc_info.value)


@pytest.mark.unit
def test_two_lane_router_dispatch():
    """Verify TwoLaneModelRouter returns the correct gateway and rejects unknown lanes."""
    fake_gw = TwoLaneModelRouter.get_lane_gateway(ModelLane.DETERMINISTIC_FAKE)
    assert "fake" in fake_gw.providers

    real_gw = TwoLaneModelRouter.get_lane_gateway(ModelLane.BUDGET_CAPPED_REAL)
    assert "fake" in real_gw.providers

    with pytest.raises(ValueError) as exc_info:
        TwoLaneModelRouter.get_lane_gateway("unsupported_lane_xyz")
    assert "Unknown model lane" in str(exc_info.value)


@pytest.mark.unit
def test_disposable_db_manager_cleanup_all():
    """Verify cleanup_all handles empty or active databases gracefully without raising."""
    manager = DisposableDatabaseManager()
    manager.active_databases.add("rebase_test_non_existent_mock_db")
    # Must run without crashing
    manager.cleanup_all()
    assert "rebase_test_non_existent_mock_db" not in manager.active_databases
