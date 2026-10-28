import sys
import os
import asyncio
sys.path.insert(0, os.path.abspath("."))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.workflow import WorkflowGate
from app.models.artifact import Artifact
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        print("=== CHECKING JOB a5752d54-9a36-4501-8bbd-a8874859ad8e ===")
        res = await db.execute(select(Job).filter(Job.job_id == "a5752d54-9a36-4501-8bbd-a8874859ad8e"))
        j = res.scalar_one_or_none()
        if j:
            print(f"Target Job Found: {j.job_id} status={j.status} name={j.name}")
        else:
            print("Target Job NOT found in DB")

        print("=== G3 GATES ===")
        res = await db.execute(select(WorkflowGate).filter(WorkflowGate.gate_type == "G3"))
        for g in res.scalars().all():
            print(f"Gate: {g.gate_id} job={g.job_id} status={g.status} artifacts={g.artifact_ids} hashes={g.artifact_hashes}")

        print("=== ALL COMPLETED/VERIFIED MODULE ATTEMPTS ===")
        res = await db.execute(select(ModuleAttempt).filter(ModuleAttempt.status.in_(["VERIFIED", "COMPLETED", "APPROVED"])))
        for a in res.scalars().all():
            print(f"Attempt: {a.attempt_id} module={a.module_id} num={a.attempt_number} status={a.status} commit={a.commit_sha}")

if __name__ == "__main__":
    asyncio.run(main())
