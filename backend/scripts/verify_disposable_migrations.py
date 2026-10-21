"""Script to independently verify Alembic migrations on a fresh disposable PostgreSQL database."""

import asyncio
import os
from alembic import command
from alembic.config import Config
import asyncpg


async def create_db(maintenance_url: str):
    conn = await asyncpg.connect(maintenance_url)
    try:
        await conn.execute("DROP DATABASE IF EXISTS rebase_audit_disposable_test WITH (FORCE);")
        await conn.execute("CREATE DATABASE rebase_audit_disposable_test;")
        print("PASS: Created fresh disposable database 'rebase_audit_disposable_test'.")
    finally:
        await conn.close()


async def verify_and_cleanup(maintenance_url: str, disposable_pg_url: str):
    test_conn = await asyncpg.connect(disposable_pg_url)
    try:
        rows = await test_conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        )
        tables = [r["table_name"] for r in rows]
        print(f"PASS: Verified {len(tables)} tables created in disposable database:")
        for t in tables:
            print(f"  - {t}")

        rev = await test_conn.fetchval("SELECT version_num FROM alembic_version;")
        print(f"PASS: Active migration revision recorded in alembic_version: {rev}")

        expected_tables = {
            "agent_runs", "alembic_version", "artifacts", "audit_events",
            "budget_usage", "gate_decisions", "job_memberships", "jobs", "module_attempts",
            "modules", "roles", "test_cases", "test_results", "user_sessions", "users"
        }
        missing = expected_tables - set(tables)
        if missing:
            raise RuntimeError(f"Missing expected tables: {missing}")
        print(f"PASS: All {len(expected_tables)} expected tables (including alembic_version) verified!")
    finally:
        await test_conn.close()

    # Clean up disposable database
    cleanup_conn = await asyncpg.connect(maintenance_url)
    try:
        await cleanup_conn.execute("DROP DATABASE rebase_audit_disposable_test WITH (FORCE);")
        print("PASS: Dropped disposable database 'rebase_audit_disposable_test' cleanly.")
    finally:
        await cleanup_conn.close()


def main():
    maintenance_url = "postgresql://postgres:postgres123@localhost:5433/postgres"
    disposable_async_url = "postgresql+asyncpg://postgres:postgres123@localhost:5433/rebase_audit_disposable_test"
    disposable_pg_url = "postgresql://postgres:postgres123@localhost:5433/rebase_audit_disposable_test"

    print(f"Connecting to maintenance DB on {maintenance_url}...")
    asyncio.run(create_db(maintenance_url))

    os.environ["DATABASE_URL"] = disposable_async_url
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", disposable_async_url)

    print("Running 'alembic upgrade head' against disposable database...")
    command.upgrade(alembic_cfg, "head")
    print("PASS: 'alembic upgrade head' executed successfully!")

    print("Verifying schema and dropping disposable database...")
    asyncio.run(verify_and_cleanup(maintenance_url, disposable_pg_url))
    print("ALL MIGRATION CHECKS PASSED ON DISPOSABLE POSTGRESQL DATABASE!")


if __name__ == "__main__":
    main()
