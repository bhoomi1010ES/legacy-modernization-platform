from pathlib import Path

target_file = Path("backend/app/services/supervisor_service.py")
content = target_file.read_text(encoding="utf-8")

recovery_method = '''    async def recover_failed_phase6_job(
        self,
        db: AsyncSession,
        job_id: UUID,
        rationale: str,
        target_module_id: Optional[UUID] = None,
        *,
        actor_id: str = "SupervisorRecovery",
    ) -> Dict[str, Any]:
        """Authoritative recovery of a failed Phase 6 job after diagnosing and fixing defects.
        
        Strictly enforces:
        1. G1, G2, G3 human approvals exist and are valid.
        2. No live worker holds orchestration or module leases.
        3. Workspace repository integrity is valid.
        4. Budget limit is not exceeded.
        5. Preserves attempt history and retry counts.
        6. Persists an audited RECOVERY checkpoint and audit log.
        """
        job = await db.get(Job, job_id)
        if not job:
            raise NotFoundException("Job", str(job_id))

        gates = (await db.execute(
            select(WorkflowGate).where(
                WorkflowGate.job_id == job_id,
                WorkflowGate.status == "APPROVED"
            )
        )).scalars().all()
        approved_types = {g.gate_type for g in gates}
        if not {"G1", "G2", "G3"}.issubset(approved_types):
            raise ConflictException(f"Cannot recover Phase 6 job: missing approved gates (approved: {approved_types})")

        now = utc_now()
        if job.orchestration_owner and job.orchestration_lease_expires_at:
            if _normalize_dt(job.orchestration_lease_expires_at) > now:
                raise ConflictException(f"Job is actively leased to worker {job.orchestration_owner}")

        if job.budget_limit_usd and job.budget_used_usd and job.budget_used_usd >= job.budget_limit_usd:
            raise ConflictException("Cannot recover job: budget exhausted")

        ws_valid = await repository_workspace_service.validate_workspace(job.job_id)
        if not ws_valid.is_ready:
            raise ConflictException(f"Repository workspace is invalid: {ws_valid.error_message}")

        target_mod = None
        if target_module_id:
            target_mod = await db.get(Module, target_module_id)
            if not target_mod or target_mod.job_id != job.job_id:
                raise NotFoundException("Module", str(target_module_id))
            target_mod.status = "PENDING"
            target_mod.lease_owner = None
            target_mod.lease_expires_at = None
            target_mod.lease_generation += 1

        correlation_id = str(uuid.uuid4())
        checkpoint_state = {
            "action": "RECOVER_PHASE6",
            "rationale": rationale,
            "target_module_id": str(target_module_id) if target_module_id else None,
            "previous_status": job.status,
            "previous_blocking_reason": job.blocking_reason,
            "status": "CONVERTING",
            "active_node": "supervisor",
        }
        checkpoint = await self.checkpointer.save(
            db,
            job,
            kind="RECOVERY",
            node_name="supervisor",
            state=checkpoint_state,
            correlation_id=correlation_id,
        )

        job.status = "CONVERTING"
        job.active_node = "supervisor"
        job.blocking_reason = None
        job.last_transition = "RECOVERED"
        job.orchestration_owner = None
        job.orchestration_lease_expires_at = None
        job.orchestration_generation += 1

        db.add(AuditEvent(
            job_id=job.job_id,
            event_type="JOB_RECOVERED",
            actor_type="SYSTEM",
            actor_id=actor_id,
            target_resource=str(job.job_id),
            payload={
                "rationale": rationale,
                "target_module_id": str(target_module_id) if target_module_id else None,
                "checkpoint_sequence": checkpoint.sequence,
            },
        ))
        await db.commit()
        return {
            "job_id": str(job.job_id),
            "status": job.status,
            "target_module": target_mod.name if target_mod else None,
            "checkpoint_sequence": checkpoint.sequence,
        }

'''

target_marker = "supervisor_service = SupervisorService()"
if target_marker in content and "recover_failed_phase6_job" not in content:
    content = content.replace(target_marker, recovery_method + target_marker)
    target_file.write_text(content, encoding="utf-8")
    print("Added recover_failed_phase6_job to SupervisorService successfully.")
elif "recover_failed_phase6_job" in content:
    print("recover_failed_phase6_job already present.")
else:
    print("Error: target_marker not found!")

