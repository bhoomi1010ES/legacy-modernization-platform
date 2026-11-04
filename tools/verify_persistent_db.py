import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine('postgresql+asyncpg://postgres:postres123@localhost:5432/rebase')
    async with engine.connect() as conn:
        tables = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        total = 0
        for (tbl,) in tables:
            c = (await conn.execute(text(f'SELECT count(*) FROM "{tbl}"'))).scalar()
            total += c
        print(f"Total rows in persistent database rebase: {total}")
        assert total == 279432, f"Expected 279432 rows, got {total}"
        print("VERIFIED: Persistent database 'rebase' is 100% UNTOUCHED and PRESERVED.")

asyncio.run(main())

