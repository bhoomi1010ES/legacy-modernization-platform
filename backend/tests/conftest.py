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
