import asyncio
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.workflow import WorkflowGate
from app.models.artifact import Artifact
from app.models.module import Module
from app.schemas.jobs import JobStatus
from app.services.supervisor_service import supervisor_service

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        print(f"Current Job Status: {job.status}")
        
        if job.status == "PLANNING":
            print("Transitioning Job from PLANNING to AWAITING_GATE_G3...")
            await supervisor_service.transition(
                db,
                job.job_id,
                JobStatus.AWAITING_GATE_G3,
                reason="Planning complete and verified acyclic; Gate G3 pending human review.",
                actor_id="bbacac52-6e67-43a3-9983-3ad6354343d2",
            )
            await db.commit()
            await db.refresh(job)
            print(f"Updated Job Status: {job.status}")

        # Check Gate G3
        g3_gate = await db.scalar(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job_id,
                WorkflowGate.gate_type == "G3",
                WorkflowGate.status == "PENDING",
            ).order_by(WorkflowGate.version.desc()).limit(1)
        )
        if g3_gate:
            print(f"\nGate G3 is PENDING human review!")
            print(f"  Gate ID: {g3_gate.gate_id}")
            print(f"  Version: {g3_gate.version}")
            print(f"  Artifact Hashes: {g3_gate.artifact_hashes}")
        
        # Check Modules
        modules = (await db.execute(select(Module).where(Module.job_id == job_id).order_by(Module.wave_number.asc()))).scalars().all()
        print(f"\nModules in DAG ({len(modules)}):")
        waves = {}
        for m in modules:
            waves.setdefault(m.wave_number, []).append(m)
        for w in sorted(waves):
            print(f"  --- WAVE {w} ({len(waves[w])} modules) ---")
            for m in waves[w]:
                print(f"    Module: {m.name} | id: {m.module_id} | status: {m.status} | target: {m.target_path} | deps: {m.dependency_module_ids}")

if __name__ == "__main__":
    asyncio.run(main())

