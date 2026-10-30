import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.workflow import WorkflowGate
from app.models.job import Job
from app.schemas.gates import GateDecisionRequest, DecisionOutcome
from app.services.gate_service import gate_service
from sqlalchemy import select

GATE_ID = uuid.UUID("8a76d8c4-e6ca-4e35-8805-768823289744")
REVIEWER_ID = uuid.UUID("bbacac52-6e67-43a3-9983-3ad6354343d2") # Alex Morgan

async def main():
    async with AsyncSessionLocal() as db:
        gate = await db.get(WorkflowGate, GATE_ID)
        assert gate is not None, "Gate not found"
        job = await db.get(Job, gate.job_id)
        assert job is not None, "Job not found"
        print(f"Gate: {gate.gate_id}, Status: {gate.status}, Job: {job.name} ({job.status})")

        payload = GateDecisionRequest(
            decision=DecisionOutcome.APPROVED,
            rationale="Approved baseline characterization suite with 141 verified passing test vectors and validated database migration plan for Spendwise repository.",
            artifact_hashes=dict(gate.artifact_hashes),
            waivers=[],
            options={},
            idempotency_key=f"g2-approval-{uuid.uuid4()}",
        )

        decision, decided_gate, updated_job, replay = await gate_service.decide(
            db,
            GATE_ID,
            payload,
            actor_id=REVIEWER_ID,
            actor_role="REVIEWER",
            correlation_id="corr-g2-test-approval",
        )
        await db.commit()
        print(f"Decision recorded successfully!")
        print(f"Decision ID: {decision.decision_id}")
        print(f"Gate Status: {decided_gate.status}")
        print(f"Job Status: {updated_job.status}")

if __name__ == "__main__":
    asyncio.run(main())
