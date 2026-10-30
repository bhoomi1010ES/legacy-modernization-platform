import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.workflow import WorkflowGate
from app.models.job import Job
from app.services import phase5_service as service

async def main():
    async with AsyncSessionLocal() as db:
        gates = (await db.scalars(select(WorkflowGate).where(WorkflowGate.gate_type == "G2"))).all()
        for g in gates:
            job = await db.get(Job, g.job_id)
            job_name = job.name if job else "None"
            try:
                rep = await service.report(db, g.job_id)
                num_cases = len(rep.get("cases", []))
                print(f"GATE: {g.gate_id} | Status: {g.status} | Job: {g.job_id} ({job_name}) | Cases: {num_cases} | Blockers: {rep.get('g2_readiness', {}).get('blocking_reasons', [])} | SchemaStatus: {rep.get('schema_status')} | SchemaVal: {rep.get('schema_validation_status')}")
            except Exception as e:
                pass

if __name__ == "__main__":
    asyncio.run(main())
