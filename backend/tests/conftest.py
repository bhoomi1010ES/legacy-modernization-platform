"""Pytest fixtures and configuration for backend testing."""

import os
import sys
from pathlib import Path

os.environ["ENVIRONMENT"] = "testing"

# Add backend directory to Python sys.path so app modules import cleanly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from fastapi.testclient import TestClient
from app.core.database import AsyncSessionLocal
from app.main import app


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
def observed_phase5_baseline(monkeypatch):
    """Controlled adapter evidence for integration tests; never a real-sandbox acceptance claim."""
    import uuid
    from unittest.mock import AsyncMock
    from app.services import phase5_service as service
    from app.schemas.phase5 import CaptureRequest, FreezeRequest, ValidationRequest
    monkeypatch.setattr(service, "replay", AsyncMock(return_value={"available": True, "output": {"records": []}, "side_effects": {}}))

    async def prepare(db, job, actor):
        result = await service.capture(db, job, CaptureRequest.model_validate({
            "idempotency_key": str(uuid.uuid4()),
            "scenarios": [{"name": "empty records", "module": "records", "interface": "list", "behavior": "empty result", "expected": {"records": []}}],
            "tables": [{"name": "records", "columns": [{"name": "id", "type": "INTEGER", "primary_key": True}]}],
        }), str(actor.user_id))
        await service.validate_plan(db, job, ValidationRequest.model_validate({"tables": [{"name": "records", "rows": [{"id": 1}]}]}), str(actor.user_id))
        await service.freeze(db, job, FreezeRequest(suite_id=result["suite_id"], content_hash=result["content_hash"]))
        return result
    return prepare
