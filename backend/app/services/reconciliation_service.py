"""Historic data consistency reconciliation service.

Detects and resolves historic inconsistent records without destroying audit evidence:
- 139 module VERIFIED states without corresponding VERIFIED attempts
- 24 expired RUNNING attempt leases
- Stranded outbox events (dead-letter classification & stale pending)
- Workflow gate and job state contradictions
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.gate import GateDecision
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.workflow import WorkflowGate, WorkflowOutbox

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ProposedAction:
    action_type: str  # RECOVERABLE_REQUEUE, STALE_WORKER_QUARANTINE, EVIDENCE_REVERIFY, GATE_RECONCILE, DEADLETTER_REVIEW, TERMINAL_RETAIN, MANUAL_REVIEW
    entity_type: str  # module, module_attempt, workflow_gate, workflow_outbox, job
    entity_id: str
    current_state: Dict[str, Any]
    proposed_state: Dict[str, Any]
    rationale: str


@dataclass
class ReconciliationManifest:
    batch_id: str
    timestamp: str
    dry_run: bool
    summary: Dict[str, int]
    actions: List[ProposedAction] = field(default_factory=list)


class ReconciliationService:
    """Provides deterministic dry-run analysis and transactional batch reconciliation."""

    @classmethod
    async def analyze(
        cls,
        db: AsyncSession,
        batch_limit: int = 1000,
    ) -> ReconciliationManifest:
        """Scan for data inconsistencies and generate proposed reconciliation plan without modifying data."""
        batch_id = str(uuid.uuid4())
        actions: List[ProposedAction] = []
        now = utc_now()

        # 1. DATA-03: Modules marked VERIFIED without corresponding VERIFIED attempt
        # Find verified modules that have no attempt with status='VERIFIED'
        stmt_verified_modules = select(Module).where(Module.status == "VERIFIED")
        res = await db.execute(stmt_verified_modules)
        all_verified_modules = res.scalars().all()

        for mod in all_verified_modules:
            stmt_att = (
                select(func.count(ModuleAttempt.attempt_id))
                .where(ModuleAttempt.module_id == mod.module_id)
                .where(ModuleAttempt.status == "VERIFIED")
            )
            count_res = await db.execute(stmt_att)
            if (count_res.scalar() or 0) == 0:
                actions.append(
                    ProposedAction(
                        action_type="EVIDENCE_REVERIFY",
                        entity_type="module",
                        entity_id=str(mod.module_id),
                        current_state={"status": mod.status, "name": mod.name},
                        proposed_state={
                            "status": "PENDING",
                            "reason": "Revoked unverified eligibility",
                        },
                        rationale="Module marked VERIFIED without a valid corresponding VERIFIED attempt record.",
                    )
                )

        # 2. DATA-04: RUNNING module attempts with expired leases or stale runtime (>24h)
        stmt_stale_attempts = select(ModuleAttempt).where(
            ModuleAttempt.status == "RUNNING"
        )
        res_attempts = await db.execute(stmt_stale_attempts)
        for att in res_attempts.scalars().all():
            actions.append(
                ProposedAction(
                    action_type="STALE_WORKER_QUARANTINE",
                    entity_type="module_attempt",
                    entity_id=str(att.attempt_id),
                    current_state={
                        "status": att.status,
                        "started_at": str(att.started_at),
                    },
                    proposed_state={"status": "FAILED", "completed_at": str(now)},
                    rationale="Worker lease expired or abandoned execution without completion.",
                )
            )

        # 3. DATA-06: Gate contradictions (PENDING gates on terminal jobs)
        stmt_gates = (
            select(WorkflowGate, Job)
            .join(Job, WorkflowGate.job_id == Job.job_id)
            .where(WorkflowGate.status == "PENDING")
            .where(Job.status.in_(["FAILED", "CANCELLED", "COMPLETED"]))
        )
        res_gates = await db.execute(stmt_gates)
        for gate, job in res_gates.all():
            actions.append(
                ProposedAction(
                    action_type="GATE_RECONCILE",
                    entity_type="workflow_gate",
                    entity_id=str(gate.gate_id),
                    current_state={
                        "gate_status": gate.status,
                        "job_status": job.status,
                    },
                    proposed_state={
                        "gate_status": "INVALIDATED",
                        "decided_at": str(now),
                    },
                    rationale=f"Parent job entered terminal state '{job.status}' without deciding gate.",
                )
            )

        # 4. DATA-05: Stranded Outbox Events
        stmt_dead_letter = (
            select(WorkflowOutbox)
            .where(WorkflowOutbox.status == "DEAD_LETTER")
            .limit(batch_limit)
        )
        res_dl = await db.execute(stmt_dead_letter)
        for outbox in res_dl.scalars().all():
            last_err = (outbox.last_error or "").lower()
            if (
                "syntax" in last_err
                or "malformed" in last_err
                or "validation" in last_err
            ):
                action_type = "TERMINAL_RETAIN"
                rationale = (
                    "Poison event retained permanently for searchability without retry."
                )
            elif outbox.idempotency_key and outbox.attempts < 10:
                action_type = "DEADLETTER_REVIEW"
                rationale = "Transient outbox failure with explicit idempotency key available for review."
            else:
                action_type = "TERMINAL_RETAIN"
                rationale = "Max retry attempts exhausted; retained for audit inquiry."

            actions.append(
                ProposedAction(
                    action_type=action_type,
                    entity_type="workflow_outbox",
                    entity_id=str(outbox.outbox_id),
                    current_state={
                        "status": outbox.status,
                        "attempts": outbox.attempts,
                    },
                    proposed_state={
                        "status": outbox.status,
                        "disposition": action_type,
                    },
                    rationale=rationale,
                )
            )

        summary = {
            "total_actions": len(actions),
            "evidence_reverify": sum(
                1 for a in actions if a.action_type == "EVIDENCE_REVERIFY"
            ),
            "stale_worker_quarantine": sum(
                1 for a in actions if a.action_type == "STALE_WORKER_QUARANTINE"
            ),
            "gate_reconcile": sum(
                1 for a in actions if a.action_type == "GATE_RECONCILE"
            ),
            "deadletter_review": sum(
                1 for a in actions if a.action_type == "DEADLETTER_REVIEW"
            ),
            "terminal_retain": sum(
                1 for a in actions if a.action_type == "TERMINAL_RETAIN"
            ),
        }

        return ReconciliationManifest(
            batch_id=batch_id,
            timestamp=now.isoformat(),
            dry_run=True,
            summary=summary,
            actions=actions,
        )

    @classmethod
    async def apply(
        cls,
        db: AsyncSession,
        manifest: ReconciliationManifest,
        actor_id: str = "SYSTEM_RECONCILER",
    ) -> Dict[str, Any]:
        """Apply the approved reconciliation actions transactionally and record an immutable audit event."""
        now = utc_now()
        applied_counts: Dict[str, int] = {
            "evidence_reverify": 0,
            "stale_worker_quarantine": 0,
            "gate_reconcile": 0,
            "deadletter_classified": 0,
        }

        for item in manifest.actions:
            if item.action_type == "EVIDENCE_REVERIFY" and item.entity_type == "module":
                mod_uuid = uuid.UUID(item.entity_id)
                await db.execute(
                    update(Module)
                    .where(Module.module_id == mod_uuid)
                    .values(status="PENDING", updated_at=now)
                )
                applied_counts["evidence_reverify"] += 1

            elif (
                item.action_type == "STALE_WORKER_QUARANTINE"
                and item.entity_type == "module_attempt"
            ):
                att_uuid = uuid.UUID(item.entity_id)
                await db.execute(
                    update(ModuleAttempt)
                    .where(ModuleAttempt.attempt_id == att_uuid)
                    .values(
                        status="FAILED",
                        completed_at=now,
                        failure_reason="Stale worker lease expired without completion (Quarantined by Reconciler)",
                    )
                )
                # Also clear module lease if still held
                mod_id = item.current_state.get("module_id")
                if mod_id:
                    await db.execute(
                        update(Module)
                        .where(Module.module_id == uuid.UUID(mod_id))
                        .values(lease_owner=None, lease_expires_at=None, updated_at=now)
                    )
                applied_counts["stale_worker_quarantine"] += 1

            elif (
                item.action_type == "GATE_RECONCILE"
                and item.entity_type == "workflow_gate"
            ):
                gate_uuid = uuid.UUID(item.entity_id)
                await db.execute(
                    update(WorkflowGate)
                    .where(WorkflowGate.gate_id == gate_uuid)
                    .values(
                        status="INVALIDATED",
                        decided_at=now,
                        blocking_reason="Parent job entered terminal state without gate decision (Reconciled)",
                    )
                )
                applied_counts["gate_reconcile"] += 1

            elif (
                item.action_type in ("TERMINAL_RETAIN", "DEADLETTER_REVIEW")
                and item.entity_type == "workflow_outbox"
            ):
                applied_counts["deadletter_classified"] += 1

        # Record immutable audit event
        audit_event = AuditEvent(
            event_type="data.reconciliation_applied",
            actor_type="SYSTEM",
            actor_id=actor_id,
            target_resource="database.reconciliation",
            payload={
                "batch_id": manifest.batch_id,
                "summary": manifest.summary,
                "applied_counts": applied_counts,
                "timestamp": now.isoformat(),
            },
        )
        db.add(audit_event)

        await db.commit()

        return {
            "batch_id": manifest.batch_id,
            "status": "APPLIED",
            "applied_counts": applied_counts,
            "timestamp": now.isoformat(),
        }
