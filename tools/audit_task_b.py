import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.module import Module, ModuleAttempt
from app.models.agent import AgentRun
from app.models.audit import AuditEvent
from sqlalchemy import select

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
MODULE_ID = uuid.UUID("8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3")

async def main():
    async with AsyncSessionLocal() as db:
        print("="*80)
        print("TASK B: AUDIT CONVERSION TASK AND ATTEMPT HISTORY")
        print("="*80)

        mod = await db.get(Module, MODULE_ID)
        print(f"Module: {mod.name} ({mod.module_id})")
        print(f"Status: {mod.status}")
        print(f"Lease Owner: {mod.lease_owner}")
        print(f"Lease Expires At: {mod.lease_expires_at}")
        print(f"Lease Generation: {mod.lease_generation}")
        print(f"Budget Limit: {mod.budget_limit_usd}, Budget Used: {mod.budget_used_usd}")
        print(f"Retry Count: {mod.retry_count}")

        attempts = (await db.scalars(
            select(ModuleAttempt)
            .where(ModuleAttempt.module_id == MODULE_ID)
            .order_by(ModuleAttempt.attempt_number)
        )).all()
        print(f"\nTotal Attempts: {len(attempts)}")

        for att in attempts:
            print(f"\n--- ATTEMPT #{att.attempt_number} (ID: {att.attempt_id}) ---")
            print(f"Status: {att.status}")
            print(f"Git Branch: {att.git_branch}")
            print(f"Started At: {att.started_at}")
            print(f"Completed At: {att.completed_at}")
            print(f"Failure Reason: {att.failure_reason}")
            print(f"Lease Generation: {att.lease_generation}")
            print(f"Agent Run ID: {att.agent_run_id}")

            if att.agent_run_id:
                run = await db.get(AgentRun, att.agent_run_id)
                if run:
                    print(f"  Agent Name: {run.agent_name}")
                    print(f"  Task ID: {run.task_id}")
                    print(f"  Correlation ID: {run.correlation_id}")
                    print(f"  Model Provider: {run.model_provider}")
                    print(f"  Model Identifier: {run.model_identifier}")
                    print(f"  Input Tokens: {run.input_tokens}, Output Tokens: {run.output_tokens}")
                    print(f"  Cost USD: ${run.cost_usd}")
                    print(f"  Run Status: {run.status}")
                    print(f"  Failure Classification: {run.failure_classification}")
                    print(f"  Error Message: {run.error_message}")
                    print(f"  Task Payload Keys: {list((run.task_payload or {}).keys())}")
                    print(f"  Output Payload Keys: {list((run.output_payload or {}).keys())}")
                    if run.task_payload and "repair_context" in run.task_payload:
                        print(f"  Repair Context: {json.dumps(run.task_payload['repair_context'], indent=4)}")

        audits = (await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.job_id == JOB_ID)
            .order_by(AuditEvent.created_at)
        )).all()
        mod_audits = [a for a in audits if str(MODULE_ID) in str(a.payload) or a.target_resource == str(MODULE_ID)]
        print(f"\nAudit Events for Module ({len(mod_audits)}):")
        for a in mod_audits:
            print(f"  [{a.created_at}] Event: {a.event_type} | Actor: {a.actor_type}/{a.actor_id}")
            print(f"    Payload: {json.dumps(a.payload, indent=4)}")

if __name__ == "__main__":
    asyncio.run(main())

