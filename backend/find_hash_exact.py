import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text
from app.models.job import Job

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT gate_id, job_id, gate_type, version, status, artifact_hashes FROM workflow_gates WHERE CAST(artifact_hashes AS text) LIKE '%e60ad1d5%'"))
        rows = res.fetchall()
        for r in rows:
            job = await db.get(Job, r[1])
            job_name = job.name if job else "Unknown"
            print(f"MATCH: gate_id={r[0]} job_id={r[1]} ({job_name}) type={r[2]} v{r[3]} status={r[4]} hashes={r[5]}")

if __name__ == '__main__':
    asyncio.run(main())

