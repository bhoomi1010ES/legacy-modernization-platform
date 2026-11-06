import asyncpg
import asyncio
import json
import uuid

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    attempt_id = uuid.UUID("ca59bb7e-f9c1-4980-a0da-3af74d7f45ea")
    vr = await conn.fetchrow(
        "SELECT evidence FROM verification_runs WHERE attempt_id = $1",
        attempt_id
    )
    if vr:
        ev = json.loads(vr["evidence"])
        v = ev["verification"]
        print("assess passed?:", v.get("passed"))
        print("independent_review:", v.get("independent_review"))
        print("image_scan:", v.get("image_scan"))
        print("runtime_evidence exit_code:", v.get("runtime_evidence", {}).get("exit_code"))
        print("\nAll keys in verification:")
        for k, val in v.items():
            if k not in ("checks", "cases"):
                print(f"  {k}: {val}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
