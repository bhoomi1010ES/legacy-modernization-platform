import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import json
from pathlib import Path

async def main():
    # Read manifest from w00
    manifest_p = Path("docs/remediation/w00/DATABASE_BACKUP_AND_RESTORE_VERIFICATION.md")
    engine = create_async_engine('postgresql+asyncpg://postgres:postres123@localhost:5432/rebase')
    async with engine.connect() as conn:
        tables = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"))
        for (tbl,) in tables:
            c = (await conn.execute(text(f'SELECT count(*) FROM "{tbl}"'))).scalar()
            # Check if any new rows
            if tbl in ('user_sessions', 'audit_events'):
                print(f"{tbl}: {c}")

asyncio.run(main())

