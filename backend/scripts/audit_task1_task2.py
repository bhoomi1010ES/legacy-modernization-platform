import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.workflow import WorkflowGate
from app.models.gate import GateDecision
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.audit import AuditEvent
from app.models.test_case import TestCase
from app.models.phase4 import ConversionPlanModel, ConversionPlanModuleModel
from sqlalchemy import select, desc

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
UTILS_MODULE_ID = uuid.UUID("8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3")

async def audit():
    async with AsyncSessionLocal() as db:
        print("=" * 80)
        print("TASK 1 AUDIT: Existing Successful Module (comp_app-utils_b30e84)")
        print("=" * 80)

        # 1. G3 Decision & Audit Record
        g3_gate = (await db.execute(
            select(WorkflowGate).where(WorkflowGate.job_id == JOB_ID, WorkflowGate.gate_type == "G3")
        )).scalars().first()
        print(f"G3 Gate: id={g3_gate.gate_id}, status={g3_gate.status}, version={g3_gate.version}")
        print(f"G3 Artifact Hashes in Gate: {g3_gate.artifact_hashes}")

        g3_decision = (await db.execute(
            select(GateDecision).where(GateDecision.gate_id == g3_gate.gate_id)
        )).scalars().first()
        if g3_decision:
            print(f"G3 Decision: id={g3_decision.decision_id}, decision={g3_decision.decision}, reviewer={g3_decision.reviewer_user_id}, at={g3_decision.decided_at}")
            print(f"G3 Decision Hashes: {g3_decision.artifact_hashes}")
            print(f"G3 Decision Rationale: {g3_decision.rationale}")

        g3_audits = (await db.execute(
            select(AuditEvent).where(AuditEvent.job_id == JOB_ID, AuditEvent.event_type.like("%GATE%"))
        )).scalars().all()
        print(f"Gate Audit Events ({len(g3_audits)}):")
        for ae in g3_audits:
            print(f"  [{ae.event_type}] at {ae.created_at} by {ae.actor_id}: {ae.payload}")

        # 2. Approved ConversionPlan artifact & exact hash
        plan_arts = (await db.execute(
            select(Artifact).where(
                Artifact.job_id == JOB_ID,
                Artifact.artifact_type.in_(["CONVERSION_PLAN", "ConversionPlan"])
            ).order_by(Artifact.version.desc())
        )).scalars().all()
        print(f"\nConversionPlan Artifacts ({len(plan_arts)}):")
        for pa in plan_arts:
            print(f"  type={pa.artifact_type}, id={pa.artifact_id}, version={pa.version}, hash={pa.content_hash}")
            is_in_gate = str(pa.artifact_id) in g3_gate.artifact_hashes or pa.content_hash in g3_gate.artifact_hashes.values()
            print(f"  In G3 Gate: {is_in_gate}")

        # 3. Module comp_app-utils_b30e84 details, attempts, lease, model calls
        mod = await db.get(Module, UTILS_MODULE_ID)
        print(f"\nModule {mod.name} (id={mod.module_id}):")
        print(f"  status={mod.status}, wave={mod.wave_number}, retries={mod.retry_count}, budget_used={mod.budget_used_usd}")
        print(f"  target_path={mod.target_path}, legacy_path={mod.legacy_path}")
        print(f"  lease_owner={mod.lease_owner}, expires={mod.lease_expires_at}")

        attempts = (await db.execute(
            select(ModuleAttempt).where(ModuleAttempt.module_id == UTILS_MODULE_ID).order_by(ModuleAttempt.attempt_number.asc())
        )).scalars().all()
        print(f"Module Attempts ({len(attempts)}):")
        for att in attempts:
            print(f"  Attempt #{att.attempt_number}: id={att.attempt_id}, status={att.status}, branch={att.git_branch}, run_id={att.agent_run_id}")
            if att.failure_reason:
                print(f"    failure_reason={att.failure_reason[:150]}")
            if att.agent_run_id:
                ar = await db.get(AgentRun, att.agent_run_id)
                if ar:
                    print(f"    AgentRun: status={ar.status}, cost=${ar.cost_usd}, in/out={ar.input_tokens}/{ar.output_tokens}, duration={(ar.completed_at - ar.started_at).total_seconds() if ar.completed_at else 'n/a'}s")

        agent_runs = (await db.execute(
            select(AgentRun).where(AgentRun.job_id == JOB_ID, AgentRun.agent_name == "CodeWriter").order_by(AgentRun.started_at.asc())
        )).scalars().all()
        print(f"\nCodeWriter Agent Runs ({len(agent_runs)}):")
        for ar in agent_runs:
            print(f"  Run id={ar.run_id}, task_id={ar.task_id}, status={ar.status}, provider={ar.model_provider}, model={ar.model_identifier}, tokens in/out={ar.input_tokens}/{ar.output_tokens}, cost={ar.cost_usd}")

        # 4. Converted Module Artifacts, ChangeSets, Verifications, Reviews
        mod_arts = (await db.execute(
            select(Artifact).where(Artifact.job_id == JOB_ID).order_by(Artifact.created_at.asc())
        )).scalars().all()
        print(f"\nArtifacts for Job ({len(mod_arts)}):")
        for a in mod_arts:
            if a.artifact_type in ("CONVERTED_MODULE", "VERIFICATION_REPORT", "REVIEW_REPORT"):
                print(f"  [{a.artifact_type}] v{a.version} id={a.artifact_id} hash={a.content_hash[:16]} producing_agent={a.producing_agent}")
                print(f"    derived_from={a.derived_from}")

        from app.services.artifact_service import ArtifactService
        art_svc = ArtifactService()
        _, v_bytes = await art_svc.get_artifact_content(db, JOB_ID, uuid.UUID("01014019-d2ef-4259-8109-7778c0ff87f7"))
        _, r_bytes = await art_svc.get_artifact_content(db, JOB_ID, uuid.UUID("3208d8e6-00c9-4f2f-b783-e40fb9609cf7"))
        v_content = json.loads(v_bytes)
        r_content = json.loads(r_bytes)
        print("\n=== VERIFICATION REPORT v3 ===")
        print("Passed:", v_content.get("passed"))
        print("Keys:", list(v_content.keys()))
        print("Checks:", v_content.get("checks"))
        print("Summary:", v_content.get("summary"))
        print("Results length (cases):", len(v_content.get("cases", [])))
        if v_content.get("cases"):
            print("Passed cases count:", sum(1 for c in v_content.get("cases", []) if c.get("status") == "PASS"))
            print("Cases sample:", v_content.get("cases")[:2])

        # Check API detail agreement
        from app.services import phase6_service as p6_service
        attempt_4 = await db.get(ModuleAttempt, uuid.UUID("aadd09e9-9381-46db-a4b8-d9b5c41fcf3a"))
        att_detail = await p6_service.detail(db, attempt_4)
        print("\n=== API DETAIL VALIDATION (Attempt #4) ===")
        print("API status:", att_detail.get("status"))
        print("API git_branch:", att_detail.get("git_branch"))
        print("Evidence keys in detail:", list(att_detail.get("evidence", {}).keys()))
        print("code_hash:", att_detail.get("evidence", {}).get("code_hash"))
        print("verification_hash:", att_detail.get("evidence", {}).get("verification_hash"))
        print("review_hash:", att_detail.get("evidence", {}).get("review_hash"))
        print("Verification passed:", att_detail.get("evidence", {}).get("verification", {}).get("passed"))
        print("All 3 hashes present:", all(k in att_detail.get("evidence", {}) for k in ("code_hash", "verification_hash", "review_hash")))
        plan_art = await db.get(Artifact, uuid.UUID("94bdf934-839a-40eb-a0d3-8319ffffdfb0"))
        _, p_bytes = await art_svc.get_artifact_content(db, JOB_ID, plan_art.artifact_id)
        p_content = json.loads(p_bytes)
        print("\n=== APPROVED CONVERSION_PLAN ARTIFACT (94bdf934) ===")
        print("Plan keys:", list(p_content.keys()))
        print("Plan total_estimate_hours:", p_content.get("total_estimate_hours"))
        print("Plan is_valid_dag:", p_content.get("is_valid_dag"))
        print("Plan waves count:", len(p_content.get("waves", [])))
        for w in p_content.get("waves", []):
            print(f"  Wave #{w.get('wave_number')}: {len(w.get('modules', []))} modules")
            for m in w.get('modules', []):
                print(f"    Module: {m.get('module_id') or m.get('name')} | deps: {m.get('dependencies')} | target: {m.get('target_scope') or m.get('target_path')}")

        if p_content.get("modules"):
            print(f"\nPlan top-level modules count: {len(p_content.get('modules', []))}")
            for m in p_content.get("modules", []):
                print(f"    Module: {m.get('module_id') or m.get('name')} | deps: {m.get('dependencies')} | wave: {m.get('wave_number')}")
        print("\nPlan top-level dependencies:", p_content.get("dependencies"))
        print("\n=== REVIEW REPORT v3 ===")
        print("Keys:", list(r_content.keys()))
        print("Review status:", r_content.get("status"))
        print("Findings count:", len(r_content.get("findings", [])))
        print("Findings:", r_content.get("findings"))

        print("\n" + "=" * 80)
        print("TASK 2 AUDIT: ConversionPlan DAG, Dependencies and Waves")
        print("=" * 80)

        plan = await db.scalar(select(ConversionPlanModel).where(ConversionPlanModel.job_id == JOB_ID).order_by(ConversionPlanModel.version.desc()).limit(1))
        print(f"ConversionPlanModel: id={plan.plan_id}, version={plan.version}, is_valid_dag={plan.is_valid_dag}, validation_status={plan.validation_status}")
        print(f"Validation payload: {plan.validation_payload}")

        plan_modules = (await db.execute(
            select(ConversionPlanModuleModel).where(ConversionPlanModuleModel.plan_id == plan.plan_id)
        )).scalars().all()
        print(f"Plan Modules Count: {len(plan_modules)}")
        for pm in plan_modules:
            p = pm.payload or {}
            print(f"  PM id={pm.module_id} wave={pm.wave_number} resp={pm.responsibility}")
            print(f"     dependencies={p.get('dependencies')} depends_on={p.get('depends_on')} target_scope={p.get('target_scope')}")

        all_mods = (await db.execute(select(Module).where(Module.job_id == JOB_ID))).scalars().all()
        print(f"\nLive Module records in DB ({len(all_mods)}):")
        for m in all_mods:
            print(f"  Module {m.name} (id={m.module_id}): wave={m.wave_number}, status={m.status}, deps={m.dependency_module_ids}")

if __name__ == "__main__":
    asyncio.run(audit())
