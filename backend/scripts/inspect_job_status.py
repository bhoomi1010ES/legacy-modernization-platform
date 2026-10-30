import asyncio
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.gate import GateDecision
from app.models.workflow import WorkflowGate
from app.models.artifact import Artifact
from app.models.module import Module
from app.models.test_case import TestCase

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        print(f"Job: {job.job_id} | Name: {job.name} | Status: {job.status}")
        
        gates = (await db.execute(select(WorkflowGate).where(WorkflowGate.job_id == job_id).order_by(WorkflowGate.gate_type, WorkflowGate.version))).scalars().all()
        print(f"\nGates ({len(gates)}):")
        for g in gates:
            print(f"  [{g.gate_type}] v{g.version} status={g.status} id={g.gate_id}")
            print(f"    artifact_hashes={g.artifact_hashes}")
            decisions = (await db.execute(select(GateDecision).where(GateDecision.gate_id == g.gate_id))).scalars().all()
            for d in decisions:
                print(f"      Decision: {d.decision} by {d.reviewer_user_id} at {d.decided_at}")
        
        artifacts = (await db.execute(select(Artifact).where(Artifact.job_id == job_id).order_by(Artifact.artifact_type, Artifact.version))).scalars().all()
        print(f"\nArtifacts ({len(artifacts)}):")
        for a in artifacts:
            print(f"  [{a.artifact_type}] v{a.version} hash={a.content_hash[:16]}... id={a.artifact_id}")
            
        modules = (await db.execute(select(Module).where(Module.job_id == job_id))).scalars().all()
        print(f"\nModules ({len(modules)}):")
        for m in modules:
            print(f"  Module: {m.name} | wave={m.wave_number} | status={m.status} | target={m.target_path}")

        test_cases_count = len((await db.execute(select(TestCase).where(TestCase.job_id == job_id))).scalars().all())
        print(f"\nTest cases count: {test_cases_count}")

if __name__ == "__main__":
    asyncio.run(main())
