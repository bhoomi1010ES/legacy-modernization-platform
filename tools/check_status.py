import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.module import Module, ModuleAttempt
from app.models.job import Job
from sqlalchemy import select

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")

async def main():
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, JOB_ID)
        print(f"Job: {job.job_id}, status={job.status}, phase={job.workflow_phase}, max_repair={job.max_repair_attempts}")
        mods = (await db.scalars(select(Module).where(Module.job_id == JOB_ID))).all()
        for m in sorted(mods, key=lambda x: x.name):
            attempts = (await db.scalars(select(ModuleAttempt).where(ModuleAttempt.module_id == m.module_id).order_by(ModuleAttempt.attempt_number.desc()))).all()
            print(f"{m.name:30}: status={m.status:15} attempts={len(attempts)} last_attempt={attempts[0].status if attempts else None} (attempt #{attempts[0].attempt_number if attempts else 0})")

if __name__ == "__main__":
    asyncio.run(main())

