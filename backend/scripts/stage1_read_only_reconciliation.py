"""Stage 1: Read-Only State Reconciliation Script for Spendwise Modernization Job.

This script performs 100% read-only queries with explicit rollback.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.workflow import WorkflowGate, WorkflowCheckpoint
from app.models.gate import GateDecision
from app.models.user import User
from app.models.module import Module, ModuleAttempt
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.agent import AgentRun

TARGET_JOB_ID = UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")

async def reconcile():
    async with AsyncSessionLocal() as db:
        print("=== 1. JOB STATUS & DETAILS ===")
        job = await db.get(Job, TARGET_JOB_ID)
        if not job:
            print("ERROR: Job not found!")
            return
        print(f"Job ID: {job.job_id}")
        print(f"Name: {job.name}")
        print(f"Status: {job.status}")
        print(f"Active Node: {job.active_node}")
        print(f"Blocking Reason: {job.blocking_reason}")
        print(f"Budget Used: ${float(job.budget_used_usd):.4f} / Limit: ${float(job.budget_limit_usd):.2f}")
        print(f"Orchestration Owner: {job.orchestration_owner}")
        print(f"Orchestration Lease Expires: {job.orchestration_lease_expires_at}")
        print(f"Orchestration Generation: {job.orchestration_generation}")
        print(f"Last Transition: {job.last_transition}")
        print(f"Workflow Phase: {job.workflow_phase}")
        print(f"Updated At: {job.updated_at}")

        print("\n=== 2. LATEST 10 AUDIT EVENTS ===")
        events = (await db.scalars(
            select(AuditEvent)
            .where(AuditEvent.job_id == TARGET_JOB_ID)
            .order_by(AuditEvent.created_at.desc())
            .limit(10)
        )).all()
        for e in events:
            print(f"[{e.created_at}] {e.event_type} | actor={e.actor_id} | payload={e.payload}")

        print("\n=== 3. G1-G4 GATES ===")
        gates = (await db.scalars(
            select(WorkflowGate)
            .where(WorkflowGate.job_id == TARGET_JOB_ID)
            .order_by(WorkflowGate.gate_type.asc(), WorkflowGate.version.asc())
        )).all()
        for g in gates:
            decision = await db.scalar(
                select(GateDecision)
                .where(GateDecision.gate_id == g.gate_id)
                .order_by(GateDecision.decided_at.desc())
                .limit(1)
            )
            reviewer_name = "N/A"
            if decision:
                user = await db.get(User, decision.reviewer_user_id)
                reviewer_name = user.email if user else str(decision.reviewer_user_id)
            print(f"Gate {g.gate_type} v{g.version}: gate_id={g.gate_id} status={g.status} requested_at={g.requested_at} decided_at={g.decided_at}")
            print(f"   Hashes: {g.artifact_hashes}")
            if decision:
                print(f"   Decision: {decision.decision} | Reviewer: {reviewer_name} | Rationale: {decision.rationale}")
            else:
                print(f"   Decision: No recorded GateDecision row")

        print("\n=== 4. ALL 14 MODULES & CURRENT STATE ===")
        modules = (await db.scalars(
            select(Module)
            .where(Module.job_id == TARGET_JOB_ID)
            .order_by(Module.wave_number.asc(), Module.name.asc())
        )).all()
        print(f"Total Modules: {len(modules)}")
        for m in modules:
            latest_att = await db.scalar(
                select(ModuleAttempt)
                .where(ModuleAttempt.module_id == m.module_id)
                .order_by(ModuleAttempt.attempt_number.desc())
                .limit(1)
            )
            att_info = f"Att #{latest_att.attempt_number} ({latest_att.status})" if latest_att else "No attempts"
            
            # Check changeset artifact for commit
            art = await db.scalar(
                select(Artifact)
                .where(Artifact.module_id == m.module_id, Artifact.artifact_type.in_(("CHANGESET", "MODULE_CODE")))
                .order_by(Artifact.version.desc())
                .limit(1)
            )
            commit = art.extra_metadata.get("commit_hash") if art and art.extra_metadata else None
            commit_info = f"commit={commit[:8]}" if commit else "no commit"
            print(f"Wave {m.wave_number} | {m.name:30} | Status: {m.status:10} | Retries: {m.retry_count} | {att_info:20} | {commit_info:16} | Lease: {m.lease_owner} (exp: {m.lease_expires_at})")

        print("\n=== 5. DETAILED INSPECTION: comp_app-models_681831 ===")
        models_mod = next((m for m in modules if "models" in m.name), None)
        if models_mod:
            print(f"Module ID: {models_mod.module_id}")
            print(f"Module Status: {models_mod.status}")
            print(f"Lease Owner: {models_mod.lease_owner}")
            print(f"Lease Expires At: {models_mod.lease_expires_at}")
            print(f"Lease Generation: {models_mod.lease_generation}")
            print(f"Retry Count: {models_mod.retry_count}")
            attempts = (await db.scalars(
                select(ModuleAttempt)
                .where(ModuleAttempt.module_id == models_mod.module_id)
                .order_by(ModuleAttempt.attempt_number.asc())
            )).all()
            print(f"Total Attempts: {len(attempts)}")
            for att in attempts[-5:]:  # show last 5
                print(f"  Attempt #{att.attempt_number}: status={att.status} branch={att.git_branch} started={att.started_at} completed={att.completed_at}")
                print(f"    Failure Reason: {att.failure_reason}")

            # Agent runs for models_mod
            runs = (await db.scalars(
                select(AgentRun)
                .where(AgentRun.job_id == TARGET_JOB_ID, AgentRun.task_id == f"p6-{models_mod.module_id}")
                .order_by(AgentRun.started_at.desc())
                .limit(5)
            )).all()
            print(f"\n  Latest {len(runs)} Agent Runs for comp_app-models_681831:")
            for r in runs:
                print(f"    Run {r.run_id} | Agent: {r.agent_name} | Status: {r.status} | Tokens: in={r.input_tokens} out={r.output_tokens} | Cost: ${float(r.cost_usd or 0):.4f}")
                print(f"    Error: {r.error_message}")
                if r.trace_payload:
                    print(f"    Trace keys: {list(r.trace_payload.keys())}")
                    if "error" in r.trace_payload:
                        print(f"    Trace error: {r.trace_payload.get('error')}")

        print("\n=== 6. VERIFIED MODULE COMMITS & WORKSPACE INSPECTION ===")
        verified_mods = [m for m in modules if m.status == "VERIFIED"]
        print(f"Verified modules count: {len(verified_mods)}")
        repo_ws = Path(f"repo_workspaces/job_{TARGET_JOB_ID}")
        print(f"Repo workspace exists: {repo_ws.exists()} at {repo_ws.resolve()}")
        if repo_ws.exists():
            for m in verified_mods:
                art = await db.scalar(
                    select(Artifact)
                    .where(Artifact.module_id == m.module_id, Artifact.artifact_type.in_(("CHANGESET", "MODULE_CODE")))
                    .order_by(Artifact.version.desc())
                    .limit(1)
                )
                commit = art.extra_metadata.get("commit_hash") if art and art.extra_metadata else None
                git_check = "NO COMMIT"
                if commit:
                    res = subprocess.run(["git", "cat-file", "-t", commit], cwd=str(repo_ws), capture_output=True, text=True)
                    git_check = f"git object: {res.stdout.strip()}" if res.returncode == 0 else f"git error: {res.stderr.strip()}"
                print(f"  {m.name:30} | Commit: {commit} | {git_check}")

        print("\n=== 7. ACTIVE/EXPIRED TASKS & LEASES ===")
        leased_modules = [m for m in modules if m.status in ("LEASED", "RUNNING") or m.lease_owner is not None]
        print(f"Modules with lease / running state: {len(leased_modules)}")
        for m in leased_modules:
            print(f"  {m.name}: status={m.status} lease_owner={m.lease_owner} expires={m.lease_expires_at} gen={m.lease_generation}")

        print("\n=== 8. LANGGRAPH CHECKPOINTS FOR JOB ===")
        cps = (await db.scalars(
            select(WorkflowCheckpoint)
            .where(WorkflowCheckpoint.job_id == TARGET_JOB_ID)
            .order_by(WorkflowCheckpoint.sequence.desc())
            .limit(5)
        )).all()
        print(f"Latest {len(cps)} Checkpoints:")
        for cp in cps:
            print(f"  Seq {cp.sequence}: node={cp.node_name} kind={cp.checkpoint_kind} created={cp.created_at}")

        await db.rollback()
        print("\nDone (Read-only transaction rolled back).")

if __name__ == '__main__':
    asyncio.run(reconcile())
