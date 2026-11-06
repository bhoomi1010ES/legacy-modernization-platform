import asyncpg
import asyncio
import json
import uuid

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    vr = await conn.fetchrow(
        "SELECT evidence FROM verification_runs WHERE attempt_id = $1",
        uuid.UUID("54673f2b-bd5b-41ca-9dab-4c14d82ef2f9")
    )
    if vr:
        ev = json.loads(vr["evidence"]) if isinstance(vr["evidence"], str) else vr["evidence"]
        for c in ev.get("verification", {}).get("checks", []):
            if c.get("category") == "static":
                print("=== MYPY STDOUT ===")
                print(c.get("stdout"))
                print("=== MYPY STDERR ===")
                print(c.get("stderr"))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

