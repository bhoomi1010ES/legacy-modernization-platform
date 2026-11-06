import asyncpg
import asyncio
import json

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    attempt_id = "c3384d67-882a-41f4-8fcd-a0b03a2a4280"
    
    vr = await conn.fetchrow("SELECT * FROM verification_runs WHERE attempt_id = $1", attempt_id)
    if vr:
        ev = json.loads(vr["evidence"]) if isinstance(vr["evidence"], str) else vr["evidence"]
        print("Keys:", list(ev.keys()))
        print("Full evidence preview:", json.dumps(ev, indent=2)[:2000])
            
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
