"""Pytest fixtures and configuration for backend testing with hermetic isolation."""

import os
import sys
import tempfile
from pathlib import Path

# Add backend directory to Python sys.path so app modules import cleanly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Configure testing environment flags
os.environ["ENVIRONMENT"] = "testing"

# Import isolation infrastructure
from app.core.testing_infrastructure import (
    DisposableDatabaseManager,
    IsolationGuard,
    ProtectedResourceError,
    IsolationTokenError,
    disposable_db_manager,
)

# Enforce or generate TEST_ISOLATION_TOKEN
isolation_token = os.getenv("TEST_ISOLATION_TOKEN")
if not isolation_token:
    isolation_token = disposable_db_manager.generate_isolation_token()

# Determine database URL target
default_test_url = (
    "postgresql+asyncpg://postgres:postres123@localhost:5432/rebase_test_w01"
)
target_db_url = os.getenv(
    "TEST_DATABASE_URL", os.getenv("DATABASE_URL", default_test_url)
)

# Strict isolation guard verification
IsolationGuard.verify_database_url(target_db_url, isolation_token)
os.environ["DATABASE_URL"] = target_db_url

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.main import app

import pytest
from fastapi.testclient import TestClient
from tests.fixtures.fixture_loader import ReferenceFixtureLoader
from app.services.model_gateway import build_fake_gateway, ModelGateway, ModelLane


@pytest.fixture(scope="session")
def test_isolation_token() -> str:
    """Provides the active cryptographic test isolation token."""
    return os.environ.get("TEST_ISOLATION_TOKEN", isolation_token)


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Provides a thread-safe FastAPI TestClient instance."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def db_session():
    """Provides an isolated async SQLAlchemy session for test execution."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
def temp_artifact_storage():
    """Provides an isolated temporary directory for test artifact storage."""
    with tempfile.TemporaryDirectory(prefix="rebase_test_storage_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        IsolationGuard.verify_storage_path(tmp_path)
        yield tmp_path


@pytest.fixture
def reference_fixtures():
    """Provides access to committed synthetic reference repositories."""
    return ReferenceFixtureLoader


@pytest.fixture
def deterministic_fake_gateway() -> ModelGateway:
    """Provides pre-configured deterministic fake model gateway for unit/CI tests."""
    return build_fake_gateway()


@pytest.fixture
def disposable_postgres_db():
    """Provisions a disposable PostgreSQL database with migrations and guaranteed teardown."""
    manager = DisposableDatabaseManager()
    db_name = manager.create_database()
    try:
        manager.run_migrations(db_name, backend_dir=backend_dir)
        db_url = f"postgresql+asyncpg://postgres:postres123@localhost:5432/{db_name}"
        yield {"name": db_name, "url": db_url, "manager": manager}
    finally:
        manager.drop_database(db_name)


@pytest.fixture
def observed_phase5_baseline(monkeypatch):
    """Controlled adapter evidence for integration tests; never a real-sandbox acceptance claim."""
    import uuid
    from unittest.mock import AsyncMock
    from app.services import phase5_service as service
    from app.schemas.phase5 import CaptureRequest, FreezeRequest, ValidationRequest

    monkeypatch.setattr(
        service,
        "replay",
        AsyncMock(
            return_value={
                "available": True,
                "output": {"records": []},
                "side_effects": {},
            }
        ),
    )

    async def prepare(db, job, actor):
        result = await service.capture(
            db,
            job,
            CaptureRequest.model_validate(
                {
                    "idempotency_key": str(uuid.uuid4()),
                    "scenarios": [
                        {
                            "name": "empty records",
                            "module": "records",
                            "interface": "list",
                            "behavior": "empty result",
                            "expected": {"records": []},
                        }
                    ],
                    "tables": [
                        {
                            "name": "records",
                            "columns": [
                                {"name": "id", "type": "INTEGER", "primary_key": True}
                            ],
                        }
                    ],
                }
            ),
            str(actor.user_id),
        )
        await service.validate_plan(
            db,
            job,
            ValidationRequest.model_validate(
                {"tables": [{"name": "records", "rows": [{"id": 1}]}]}
            ),
            str(actor.user_id),
        )
        await service.freeze(
            db,
            job,
            FreezeRequest(
                suite_id=result["suite_id"], content_hash=result["content_hash"]
            ),
        )
        return result

    return prepare
