import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.job import Job
from app.models.workflow import WorkflowGate
from app.services import phase5_service as service

async def main():
    async with AsyncSessionLocal() as db:
        jobs = (await db.scalars(select(Job).where(Job.name.like('%Spendwise%')))).all()
        for j in jobs:
            print(f"=== JOB {j.job_id} | Name: {j.name} | Status: {j.status} ===")
            gates = (await db.scalars(select(WorkflowGate).where(WorkflowGate.job_id == j.job_id))).all()
            for g in gates:
                print(f"   Gate {g.gate_id} | Type: {g.gate_type} | Status: {g.status} | Hashes: {g.artifact_hashes}")
            try:
                rep = await service.report(db, j.job_id)
                print(f"   Cases: {len(rep.get('cases', []))} | SchemaStatus: {rep.get('schema_status')} | SchemaVal: {rep.get('schema_validation_status')}")
                outcomes = {}
                for c in rep.get("cases", []):
                    o = c.get("outcome")
                    outcomes[o] = outcomes.get(o, 0) + 1
                print(f"   Outcomes: {outcomes}")
            except Exception as e:
                print(f"   Report error: {e}")

if __name__ == '__main__':
    asyncio.run(main())

