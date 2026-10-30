import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.workflow import WorkflowGate
from app.models.job import Job

async def main():
    async with AsyncSessionLocal() as db:
        gates = (await db.scalars(select(WorkflowGate).where(WorkflowGate.gate_type == "G2", WorkflowGate.status == "PENDING"))).all()
        for g in gates:
            job = await db.get(Job, g.job_id)
            print(f"PENDING G2: gate_id={g.gate_id} | job_id={g.job_id} | job_name={job.name if job else 'None'} | job_status={job.status if job else 'None'}")

if __name__ == '__main__':
    asyncio.run(main())

