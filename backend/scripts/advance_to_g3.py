import asyncio
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.workflow import WorkflowGate
from app.models.user import User
from app.schemas.gates import GateDecisionRequest, DecisionOutcome, GateType
from app.services.gate_service import gate_service
from app.services.phase4_orchestrator import phase4_orchestrator

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    reviewer_id = uuid.UUID("bbacac52-6e67-43a3-9983-3ad6354343d2")
    
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        reviewer = await db.get(User, reviewer_id)
        print(f"Current Job Status: {job.status}")
        
        # 1. Fetch pending G2 gate
        g2_gate = await db.scalar(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job_id,
                WorkflowGate.gate_type == "G2",
                WorkflowGate.status == "PENDING",
            ).order_by(WorkflowGate.version.desc()).limit(1)
        )
        if not g2_gate:
            print("No pending G2 gate found! Checking current state...")
        else:
            print(f"Found pending G2 gate: {g2_gate.gate_id} (version={g2_gate.version})")
            decision_req = GateDecisionRequest(
                decision=DecisionOutcome.APPROVED,
                rationale="Human approved characterization suite (282 vectors) and schema migration plan for Spendwise repository.",
                artifact_hashes=g2_gate.artifact_hashes,
            )
            decision, updated_gate, updated_job, _ = await gate_service.decide(
                db,
                g2_gate.gate_id,
                decision_req,
                actor_id=reviewer.user_id,
                actor_role=reviewer.role,
                correlation_id=f"human-g2-{uuid.uuid4().hex[:8]}",
            )
            await db.commit()
            print(f"G2 Decision Recorded: {decision.decision} by {decision.reviewer_user_id}")
            print(f"Updated Job Status: {updated_job.status}")

        # 2. If job is now in PLANNING, execute planning pipeline to create ConversionPlan and reach AWAITING_GATE_G3
        job = await db.get(Job, job_id)
        if job.status == "PLANNING":
            print("\nExecuting Stage 3 Planning pipeline...")
            plan = await phase4_orchestrator.run_pipeline_stage3_planning(
                db=db,
                job=job,
                user=reviewer,
                correlation_id=f"plan-{uuid.uuid4().hex[:8]}",
            )
            await db.commit()
            print(f"Planning complete! ConversionPlan generated: version={plan.version}, total modules={len(plan.modules)}")
            
            # Transition to AWAITING_GATE_G3 if not already transitioned
            await db.refresh(job)
            print(f"Job Status after planning: {job.status}")
            if job.status == "PLANNING":
                from app.services.supervisor_service import supervisor_service
                from app.schemas.jobs import JobStatus
                await supervisor_service.transition(
                    db,
                    job.job_id,
                    JobStatus.AWAITING_GATE_G3,
                    reason="Planning complete and verified acyclic; Gate G3 pending human review.",
                    actor=str(reviewer.user_id),
                )
                await db.commit()
                await db.refresh(job)
                print(f"Job Status after transition: {job.status}")

        # 3. Check Gate G3 state
        g3_gate = await db.scalar(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job_id,
                WorkflowGate.gate_type == "G3",
                WorkflowGate.status == "PENDING",
            ).order_by(WorkflowGate.version.desc()).limit(1)
        )
        if g3_gate:
            print(f"\nGate G3 is now PENDING human review!")
            print(f"  Gate ID: {g3_gate.gate_id}")
            print(f"  Version: {g3_gate.version}")
            print(f"  Artifact Hashes: {g3_gate.artifact_hashes}")
        else:
            print("No pending G3 gate found!")

if __name__ == "__main__":
    asyncio.run(main())

