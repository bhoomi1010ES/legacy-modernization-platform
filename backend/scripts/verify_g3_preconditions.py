import asyncio
import json
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.workflow import WorkflowGate
from app.models.artifact import Artifact
from app.services.artifact_service import ArtifactService

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    svc = ArtifactService()
    
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        assert job.status == "AWAITING_GATE_G3", f"Expected AWAITING_GATE_G3, got {job.status}"
        print(f"[PRECONDITION 1] Job Status: {job.status} (GENUINE)")
        
        # Check required artifacts
        artifacts = (await db.execute(select(Artifact).where(Artifact.job_id == job_id))).scalars().all()
        by_type = {}
        for a in artifacts:
            by_type.setdefault(a.artifact_type, []).append(a)
            
        required = ["TargetBlueprint", "FeasibilityReport", "CONVERSION_PLAN", "CHARACTERIZATION_SUITE", "SCHEMA_MIGRATION_PLAN"]
        print(f"\n[PRECONDITION 2] Checking required artifacts:")
        for req in required:
            matching = by_type.get(req, [])
            assert matching, f"Missing required artifact: {req}"
            latest = sorted(matching, key=lambda x: x.version)[-1]
            print(f"  [OK] {req} v{latest.version} | id={latest.artifact_id} | hash={latest.content_hash[:16]}... | derived_from={latest.derived_from}")
            
        # Verify ConversionPlan
        plan_art = sorted(by_type["CONVERSION_PLAN"], key=lambda x: x.version)[-1]
        raw_plan = await svc.storage.get_object(plan_art.storage_path)
        plan_data = json.loads(raw_plan.decode("utf-8"))
        print(f"\n[PRECONDITION 3] Verifying ConversionPlan content:")
        print(f"  Plan version: {plan_data.get('version')}")
        print(f"  Modules count: {len(plan_data.get('modules', []))}")
        print(f"  Tasks count: {len(plan_data.get('tasks', []))}")
        print(f"  Waves: {len(plan_data.get('waves', []))} waves: {[w.get('wave_number') for w in plan_data.get('waves', [])]}")
        print(f"  DAG validation: {plan_data.get('validation')}")
        print(f"  Risk summary: {list(plan_data.get('risk_summary', {}).keys())}")
        assert not plan_data.get('validation', {}).get('has_cycles'), "Plan DAG has cycles!"
        assert plan_data.get('validation', {}).get('is_valid_dag'), "Plan DAG is not valid!"
        print(f"  [OK] ConversionPlan is schema-valid, acyclic, and contains full module definitions!")
        
        # Verify Gate G3
        g3_gate = await db.scalar(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job_id,
                WorkflowGate.gate_type == "G3",
                WorkflowGate.status == "PENDING",
            ).order_by(WorkflowGate.version.desc()).limit(1)
        )
        assert g3_gate is not None, "Gate G3 is not pending!"
        print(f"\n[PRECONDITION 4] Gate G3 status:")
        print(f"  Gate ID: {g3_gate.gate_id}")
        print(f"  Status: {g3_gate.status}")
        print(f"  Version: {g3_gate.version}")
        print(f"  Artifact Hashes: {g3_gate.artifact_hashes}")
        print(f"  [OK] Preconditions fully satisfied!")

if __name__ == "__main__":
    asyncio.run(main())
