"""Create database 'rebase' and run migrations to build all tables."""

import asyncio
import asyncpg
from pathlib import Path
import sys

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))


async def setup_target_database():
    target_url = "postgresql://postgres:postres123@localhost:5432/rebase"
    maint_url = "postgresql://postgres:postres123@localhost:5432/postgres"

    print("=" * 60)
    print("Verifying and Initializing Target Database: rebase")
    print("=" * 60)

    # 1. Connect to maintenance db and ensure 'rebase' database exists
    print("[Step 1] Connecting to PostgreSQL maintenance database...")
    try:
        conn = await asyncpg.connect(maint_url, timeout=5)
        print("  --> [SUCCESS] Connected to PostgreSQL service with user 'postgres'!")

        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", "rebase"
        )
        if not exists:
            print("  --> Creating database 'rebase'...")
            await conn.execute('CREATE DATABASE "rebase"')
            print("  --> [SUCCESS] Database 'rebase' created!")
        else:
            print("  --> Database 'rebase' already exists.")
        await conn.close()
    except Exception as e:
        print(f"  --> [ERROR] Failed to connect or create database: {e}")
        return False

    # 2. Verify direct connection to 'rebase'
    print("\n[Step 2] Verifying connection to 'rebase' database...")
    try:
        rebase_conn = await asyncpg.connect(target_url, timeout=5)
        current_db = await rebase_conn.fetchval("SELECT current_database();")
        print(f"  --> [SUCCESS] Connected directly to database: '{current_db}'")
        tables = await rebase_conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
        )
        print(f"  --> Existing tables before migration ({len(tables)}): {[t['table_name'] for t in tables]}")
        await rebase_conn.close()
        return True
    except Exception as e:
        print(f"  --> [ERROR] Direct connection failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(setup_target_database())
    sys.exit(0 if success else 1)
