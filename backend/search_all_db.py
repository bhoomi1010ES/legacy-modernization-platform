import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        tables_res = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = [r[0] for r in tables_res.fetchall()]
        for t in tables:
            cols_res = await db.execute(text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{t}'"))
            cols = cols_res.fetchall()
            for col, dtype in cols:
                try:
                    q = f"SELECT {col} FROM {t} WHERE CAST({col} AS text) LIKE '%e60ad1d5%' LIMIT 5"
                    res = await db.execute(text(q))
                    rows = res.fetchall()
                    if rows:
                        print(f"FOUND in table={t} col={col}: {rows}")
                except Exception:
                    pass

if __name__ == '__main__':
    asyncio.run(main())

