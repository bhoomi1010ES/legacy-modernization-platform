import asyncpg
import asyncio
import json

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    job_id = "26b905d7-0013-4dd2-84ec-39d8809d280b"
    tcs = await conn.fetch("SELECT test_case_id, name, test_layer, is_frozen, fixture_payload FROM test_cases WHERE job_id = $1", job_id)
    print("Test cases count in DB:", len(tcs))
    for t in tcs:
        print("Test Case:", t["name"], "layer:", t["test_layer"], "frozen:", t["is_frozen"])
        print("  Payload:", t["fixture_payload"])
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

