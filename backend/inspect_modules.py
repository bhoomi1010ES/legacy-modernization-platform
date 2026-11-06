import asyncpg
import asyncio
import uuid

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    job_id = uuid.UUID("26b905d7-0013-4dd2-84ec-39d8809d280b")
    rows = await conn.fetch("SELECT name, legacy_path, target_path, wave_number, risk_level FROM modules WHERE job_id = $1 ORDER BY wave_number", job_id)
    for r in rows:
        print(f"[{r['name']}] (Wave {r['wave_number']}) legacy='{r['legacy_path']}' -> target='{r['target_path']}'")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
