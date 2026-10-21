"""Database connection verification script for Rebase platform."""

import asyncio
from pathlib import Path
import sys

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import asyncpg
from app.core.config import settings


async def check_database():
    print("=" * 60)
    print("Rebase Platform — PostgreSQL Connection Check")
    print("=" * 60)
    print(f"Configured DATABASE_URL: {settings.DATABASE_URL}")

    # Standardize URL for asyncpg
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    # 1. Test direct connection to configured URL
    print("\n[Step 1] Testing direct connection to target database...")
    try:
        conn = await asyncpg.connect(url, timeout=5)
        version = await conn.fetchval("SELECT version();")
        current_db = await conn.fetchval("SELECT current_database();")
        current_user = await conn.fetchval("SELECT current_user;")
        print("  --> [SUCCESS] Connected directly to target database!")
        print(f"      PostgreSQL Version: {version}")
        print(f"      Active Database:    {current_db}")
        print(f"      Active User:        {current_user}")
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;")
        table_names = [t['table_name'] for t in tables]
        print(f"      Migrated Tables ({len(table_names)}): {table_names}")
        await conn.close()
        return True
    except asyncpg.InvalidCatalogNameError:
        print("  --> [NOTICE] Target database does not exist yet.")
    except Exception as e:
        print(f"  --> [ERROR] Direct connection failed: {type(e).__name__}: {e}")

    # 2. If target db does not exist, connect to maintenance db 'postgres' and create it
    print("\n[Step 2] Attempting to connect to 'postgres' maintenance database...")
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    maint_url = urlunparse(parsed._replace(path="/postgres"))

    try:
        maint_conn = await asyncpg.connect(maint_url, timeout=5)
        print("  --> [SUCCESS] Connected to maintenance database 'postgres'!")

        target_db_name = parsed.path.lstrip("/") or "rebase_db"
        exists = await maint_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", target_db_name
        )

        if not exists:
            print(f"  --> Creating database '{target_db_name}'...")
            await maint_conn.execute(f'CREATE DATABASE "{target_db_name}";')
            print(f"  --> [SUCCESS] Database '{target_db_name}' created successfully!")
        else:
            print(f"  --> Database '{target_db_name}' already exists.")

        await maint_conn.close()

        # Re-test connection to newly created db
        print(f"\n[Step 3] Re-verifying connection to '{target_db_name}'...")
        conn = await asyncpg.connect(url, timeout=5)
        current_db = await conn.fetchval("SELECT current_database();")
        print(f"  --> [SUCCESS] Successfully connected to active database: '{current_db}'!")
        await conn.close()
        return True

    except Exception as e:
        print(f"  --> [ERROR] Maintenance check failed: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(check_database())
    print("\n" + "=" * 60)
    if success:
        print("RESULT: PostgreSQL connection is HEALTHY and READY.")
    else:
        print("RESULT: PostgreSQL connection FAILED. Please review credentials and port.")
    print("=" * 60)
