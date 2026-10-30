import asyncio
import hashlib
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.workflow import WorkflowGate
from app.models.gate import GateDecision
from app.models.user import User
from app.models.audit import AuditEvent
from app.models.artifact import Artifact
from app.models.module import Module
from app.core.storage import get_storage_adapter
from sqlalchemy import select

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
G3_GATE_ID = uuid.UUID("916cd13c-8a22-4d0e-9923-9f218bb4308a")
G3_DECISION_ID = uuid.UUID("3eb3c459-82f6-4469-a13c-397fa8986846")

async def main():
    async with AsyncSessionLocal() as db:
        print("="*80)
        print("TASK A: AUDIT G3 APPROVAL AND CONVERSIONPLAN INTEGRITY")
        print("="*80)

        # 1. Job and Gate existence & workflow linkage
        job = await db.get(Job, JOB_ID)
        assert job is not None, f"Job {JOB_ID} not found"
        gate = await db.get(WorkflowGate, G3_GATE_ID)
        assert gate is not None, f"Gate {G3_GATE_ID} not found"
        print(f"1. Job: {job.name} ({job.job_id})")
        print(f"   Status: {job.status}, Phase: {job.workflow_phase}")
        print(f"   Gate: {gate.gate_id}, Type: {gate.gate_type}, Version: {gate.version}")
        print(f"   Gate Status: {gate.status}")
        print(f"   Linkage Match (gate.job_id == job.job_id): {gate.job_id == job.job_id}")

        # 2. Decision details & authorized approver
        dec = await db.get(GateDecision, G3_DECISION_ID)
        assert dec is not None, f"Decision {G3_DECISION_ID} not found"
        print(f"\n2. Decision: {dec.decision_id}")
        print(f"   Outcome: {dec.decision}")
        print(f"   Timestamp: {dec.decided_at}")
        print(f"   Rationale: \"{dec.rationale}\"")
        print(f"   Reviewer ID: {dec.reviewer_user_id}")
        print(f"   Decision Gate ID Match: {dec.gate_id == gate.gate_id}")
        print(f"   Decision Job ID Match: {dec.job_id == job.job_id}")

        user = await db.get(User, dec.reviewer_user_id)
        if user:
            print(f"   Reviewer Name: {user.full_name}")
            print(f"   Reviewer Role: {user.role}")
            print(f"   Reviewer Email: {user.email}")
            print(f"   Reviewer Status: {user.status}")

        # 3. Audit Event
        audits = (await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.job_id == JOB_ID, AuditEvent.event_type.in_(["GATE_DECIDED", "WORKFLOW_TRANSITION"]))
            .order_by(AuditEvent.created_at)
        )).all()
        g3_audits = [a for a in audits if str(G3_GATE_ID) in str(a.payload) or str(G3_DECISION_ID) in str(a.payload) or a.payload.get("gate_type") == "G3"]
        print(f"\n3. G3 Audit Events Count: {len(g3_audits)}")
        for a in g3_audits:
            print(f"   Audit Event: {a.event_id} | Type: {a.event_type} | Actor: {a.actor_type}/{a.actor_id} | Created: {a.created_at}")
            print(f"   Payload: {json.dumps(a.payload, indent=4)}")

        # 4. Artifact inspection: CONVERSION_PLAN vs ConversionPlan
        print(f"\n4. Gate artifact_hashes map in G3 gate:")
        print(f"   {json.dumps(gate.artifact_hashes, indent=4)}")

        storage = get_storage_adapter()
        artifacts = (await db.scalars(
            select(Artifact)
            .where(Artifact.job_id == JOB_ID, Artifact.artifact_type.in_(["CONVERSION_PLAN", "ConversionPlan"]))
            .order_by(Artifact.created_at)
        )).all()
        print(f"\n   Found {len(artifacts)} conversion plan artifacts in DB for job:")
        for art in artifacts:
            print(f"\n   - Artifact ID: {art.artifact_id}")
            print(f"     Type: {art.artifact_type}, Version: {art.version}")
            print(f"     DB Content Hash: {art.content_hash}")
            print(f"     Storage Path: {art.storage_path}")
            print(f"     Producing Agent: {art.producing_agent}")
            print(f"     Created At: {art.created_at}")
            
            raw_bytes = await storage.get_object(art.storage_path)
            computed_sha = hashlib.sha256(raw_bytes).hexdigest()
            print(f"     Computed SHA-256: {computed_sha}")
            print(f"     Matches DB Hash?: {computed_sha == art.content_hash or computed_sha == art.content_hash.removeprefix('sha256:')}")
            
            plan_json = json.loads(raw_bytes)
            print(f"     Modules in plan: {len(plan_json.get('modules', []))}")
            mod_names = [m.get('name') for m in plan_json.get('modules', [])]
            print(f"     Contains target module ('comp_app-utils_b30e84')?: {'comp_app-utils_b30e84' in mod_names}")
            target_mod_entry = next((m for m in plan_json.get('modules', []) if m.get('name') == 'comp_app-utils_b30e84'), None)
            if target_mod_entry:
                print(f"     Target module entry: {json.dumps(target_mod_entry, indent=6)}")

        # 5. Module record in DB
        mod = await db.get(Module, uuid.UUID("8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3"))
        print(f"\n5. Module Record in DB (comp_app-utils_b30e84):")
        print(f"   Module ID: {mod.module_id}")
        print(f"   Name: {mod.name}")
        print(f"   Target Path: {mod.target_path}")
        print(f"   Legacy Path: {mod.legacy_path}")
        print(f"   Status: {mod.status}")
        print(f"   Wave Number: {mod.wave_number}")
        print(f"   Dependencies: {mod.dependency_module_ids}")
        print(f"   Retry Count: {mod.retry_count}")

if __name__ == "__main__":
    asyncio.run(main())

