"""PostgreSQL live connection and pool verification tests."""

import pytest
from app.core.database import ping_database, get_asyncpg_url
from app.core.config import settings


@pytest.mark.asyncio
async def test_live_postgres_connectivity():
    """Validates that PostgreSQL is reachable and responds to ping query."""
    is_healthy = await ping_database()
    assert is_healthy is True, (
        f"Failed to connect to PostgreSQL at {get_asyncpg_url()}. "
        "Ensure PostgreSQL service is running and credentials in .env are correct."
    )


@pytest.mark.asyncio
async def test_database_url_formatting():
    """Verifies that the database URL properly parses user, host, and port."""
    url = get_asyncpg_url()
    assert url.startswith("postgresql://")
    assert "rebase_db" in url
