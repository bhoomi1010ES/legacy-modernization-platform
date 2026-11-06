import asyncpg
import asyncio
import json

async def main():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    job_id = "26b905d7-0013-4dd2-84ec-39d8809d280b"
    events = await conn.fetch("SELECT event_type, payload FROM audit_events WHERE job_id = $1 ORDER BY created_at DESC", job_id)
    for e in events:
        if "SCHEMA" in e["event_type"] or "MIGRATION" in e["event_type"]:
            print("EVENT:", e["event_type"], e["payload"])
    
    arts = await conn.fetch("SELECT artifact_type, version, extra_metadata FROM artifacts WHERE job_id = $1", job_id)
    for a in arts:
        print("ARTIFACT:", a["artifact_type"], a["version"], a["extra_metadata"])
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

