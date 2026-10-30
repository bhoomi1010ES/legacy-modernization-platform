import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.job import Job
from app.services import phase5_service as service

async def main():
    async with AsyncSessionLocal() as db:
        jobs = (await db.scalars(select(Job))).all()
        for j in jobs:
            try:
                rep = await service.report(db, j.job_id)
                cases = rep.get("cases", [])
                unavail = sum(1 for c in cases if c.get("outcome") == "UNAVAILABLE")
                if unavail > 0 or len(cases) == 141:
                    print(f"JOB {j.job_id} | {j.name} | Total cases: {len(cases)} | Unavailable: {unavail} | Hash: {rep.get('content_hash')}")
            except Exception:
                pass

if __name__ == '__main__':
    asyncio.run(main())

