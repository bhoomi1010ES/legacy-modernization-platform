import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from sqlalchemy import select

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")

async def main():
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, JOB_ID)
        print(f"Job max_repair_attempts: {job.max_repair_attempts}")
        print(f"Job budget_limit_usd: {job.budget_limit_usd}, budget_used_usd: {job.budget_used_usd}")
        
        modules = (await db.scalars(select(Module).where(Module.job_id == job.job_id))).all()
        for mod in modules:
            attempts = (await db.scalars(select(ModuleAttempt).where(ModuleAttempt.module_id == mod.module_id).order_by(ModuleAttempt.attempt_number))).all()
            print(f"\nModule: {mod.name} ({mod.module_id}) - Status: {mod.status}, retry_count: {mod.retry_count}")
            for a in attempts:
                print(f"  Attempt #{a.attempt_number}: status={a.status}, failure={a.failure_reason}")

if __name__ == "__main__":
    asyncio.run(main())

