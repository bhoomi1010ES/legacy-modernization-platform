import asyncpg
import asyncio
import json

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    attempt_id = "338e8c91-7e2a-4033-9e28-5340b8ffa698"
    
    # Check agent run output payload
    ar = await conn.fetchrow("SELECT output_payload FROM agent_runs WHERE task_id = 'p6-3037b367-9909-5002-b5e7-d48c8f50c9af' ORDER BY completed_at DESC LIMIT 1")
    if ar:
        payload = json.loads(ar["output_payload"]) if isinstance(ar["output_payload"], str) else ar["output_payload"]
        print("Generated files:")
        for f in payload.get("files", {}).keys():
            print(" ", f)
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

