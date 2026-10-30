import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.workflow import WorkflowGate

async def main():
    async with AsyncSessionLocal() as db:
        jobs = (await db.execute(select(Job))).scalars().all()
        for j in jobs:
            print(f"Job: {j.job_id} | Name: {j.name} | Status: {j.status}")
            gates = (await db.execute(select(WorkflowGate).where(WorkflowGate.job_id == j.job_id))).scalars().all()
            for g in gates:
                print(f"   Gate {g.gate_type} v{g.version}: status={g.status} id={g.gate_id}")

if __name__ == "__main__":
    asyncio.run(main())

