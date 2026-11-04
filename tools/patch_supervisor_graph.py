import re

path = r"backend/app/services/supervisor_graph.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update execute_agent
old_pattern = re.compile(
    r'(\s+elif agent_name in \("ARCHITECT", "ArchitectAgent"\):[\s\S]+?return \{"execution_verdict": "SUCCESS"\}\n)',
    re.MULTILINE
)

replacement = '''            elif agent_name in ("ARCHITECT", "ArchitectAgent"):
                from app.models.phase4 import LegacyModelRecord
                from app.schemas.phase4 import LegacyModel
                from app.services.architect_agent import architect_agent
                leg_rec = (await db.execute(
                    select(LegacyModelRecord).where(LegacyModelRecord.job_id == job.job_id).order_by(LegacyModelRecord.version.desc())
                )).scalars().first()
                if not leg_rec:
                    logger.error("ArchitectAgent invoked without prerequisite LegacyModelRecord | job_id=%s", job.job_id)
                    return {
                        "execution_verdict": "ESCALATE",
                        "blocking_reason": "Architect agent missing prerequisite LegacyModelRecord.",
                        "events": [{"type": "ARCHITECT_PREREQUISITE_MISSING"}],
                    }
                legacy_model = LegacyModel(
                    model_id=str(leg_rec.model_id), job_id=str(job.job_id), snapshot_id=str(leg_rec.snapshot_id),
                    version=leg_rec.version, modules=leg_rec.modules_payload, dependency_graph=leg_rec.dependencies_payload,
                    public_interfaces=leg_rec.interfaces_payload, persistence_entities=leg_rec.persistence_payload,
                    configurations=leg_rec.configurations_payload, test_suites=leg_rec.tests_payload, risks=leg_rec.risks_payload,
                    conflicts=leg_rec.conflicts_payload, evidence_index={}, content_hash=leg_rec.content_hash,
                )
                await architect_agent.execute_architect(db, job, legacy_model, correlation_id=corr_id)
                return {"execution_verdict": "SUCCESS", "events": [{"type": "ARCHITECT_SUCCESS"}]}

            elif agent_name in ("FEASIBILITY", "FeasibilityAgent"):
                from app.models.phase4 import LegacyModelRecord, TargetBlueprintModel
                from app.schemas.phase4 import LegacyModel, TargetBlueprint
                from app.services.feasibility_agent import feasibility_agent
                leg_rec = (await db.execute(select(LegacyModelRecord).where(LegacyModelRecord.job_id == job.job_id).order_by(LegacyModelRecord.version.desc()))).scalars().first()
                bp_rec = (await db.execute(select(TargetBlueprintModel).where(TargetBlueprintModel.job_id == job.job_id).order_by(TargetBlueprintModel.version.desc()))).scalars().first()
                if not leg_rec or not bp_rec:
                    missing = "LegacyModelRecord" if not leg_rec else "TargetBlueprintModel"
                    logger.error("FeasibilityAgent invoked without prerequisite %s | job_id=%s", missing, job.job_id)
                    return {
                        "execution_verdict": "ESCALATE",
                        "blocking_reason": f"Feasibility agent missing prerequisite {missing}.",
                        "events": [{"type": "FEASIBILITY_PREREQUISITE_MISSING"}],
                    }
                legacy_model = LegacyModel(
                    model_id=str(leg_rec.model_id), job_id=str(job.job_id), snapshot_id=str(leg_rec.snapshot_id),
                    version=leg_rec.version, modules=leg_rec.modules_payload, dependency_graph=leg_rec.dependencies_payload,
                    public_interfaces=leg_rec.interfaces_payload, persistence_entities=leg_rec.persistence_payload,
                    configurations=leg_rec.configurations_payload, test_suites=leg_rec.tests_payload, risks=leg_rec.risks_payload,
                    conflicts=leg_rec.conflicts_payload, evidence_index={}, content_hash=leg_rec.content_hash,
                )
                blueprint = TargetBlueprint(
                    blueprint_id=str(bp_rec.blueprint_id), job_id=str(job.job_id), version=bp_rec.version,
                    status=bp_rec.status, target_stack=bp_rec.target_stack, target_architecture=bp_rec.target_architecture,
                    components=bp_rec.components_payload, interfaces=bp_rec.interfaces_payload, data_model=bp_rec.data_model_payload,
                    integration_contracts=bp_rec.integration_contracts_payload, deployment_constraints=[], security_constraints=[],
                    compatibility_constraints=[], migration_constraints=[], accepted_decisions=[], open_constraints=[], evidence_refs=[],
                    created_by="supervisor", content_hash=bp_rec.content_hash,
                )
                await feasibility_agent.execute_feasibility(db, job, legacy_model, blueprint, correlation_id=corr_id)
                return {"execution_verdict": "SUCCESS", "events": [{"type": "FEASIBILITY_SUCCESS"}]}

            elif agent_name in ("CharacterizerAgent", "CHARACTERIZER"):
                from app.schemas.phase5 import CaptureRequest
                from app.services.phase5_service import capture
                from app.services.supervisor_service import supervisor_service
                await capture(db, job, CaptureRequest(idempotency_key=f"discovery-{corr_id}"), "supervisor")
                await supervisor_service.command(
                    db, job.job_id, WorkflowEvent.CHARACTERIZATION_COMPLETE,
                    actor_id="supervisor", correlation_id=corr_id,
                    reason="Characterization evidence persisted; schema/data analysis is next",
                )
                return {"execution_verdict": "SUCCESS", "events": [{"type": "CHARACTERIZATION_SUCCESS"}]}

            elif agent_name in ("SCHEMA_DATA", "SchemaDataAgent"):
                from app.services.schema_data_agent import schema_data_service
                from app.services.supervisor_service import supervisor_service
                if getattr(job, "workflow_phase", "") != "SCHEMA_DATA":
                    await supervisor_service.command(
                        db, job.job_id, WorkflowEvent.CHARACTERIZATION_COMPLETE,
                        actor_id="supervisor", correlation_id=corr_id,
                    )
                await schema_data_service.execute_schema_data_analysis(db, job, correlation_id=corr_id)
                await supervisor_service.command(
                    db, job.job_id, WorkflowEvent.SCHEMA_DATA_COMPLETE,
                    actor_id="supervisor", correlation_id=corr_id,
                    reason="Schema/data evidence ready for G2",
                )
                return {"execution_verdict": "SUCCESS", "events": [{"type": "SCHEMA_DATA_SUCCESS"}]}

            elif agent_name in ("PlannerCoordinator", "PLANNER"):
                from app.services.phase4_orchestrator import phase4_orchestrator
                await phase4_orchestrator.run_pipeline_stage3_planning(db, job, correlation_id=corr_id)
                return {"execution_verdict": "SUCCESS", "events": [{"type": "PLANNING_SUCCESS"}]}

            logger.error("Unknown or unsupported agent in execute_agent: %s", agent_name)
            return {
                "execution_verdict": "ESCALATE",
                "blocking_reason": f"Workflow failed closed: unrecognized agent identifier '{agent_name}'.",
                "events": [{"type": "UNKNOWN_AGENT_ESCALATION", "agent": agent_name}],
            }
'''

assert old_pattern.search(content), "old_pattern not found!"
content = old_pattern.sub(replacement, content, count=1)

# 2. Update node_handle_escalation
old_escalation = '''async def node_handle_escalation(state: SupervisorLoopState) -> dict:
    """15. Halts workflow and records auditable failure with blocking reason."""
    reason = state.get("blocking_reason") or "Workflow escalated due to policy violation or unrecoverable error."
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if job and JobStatus(job.status) not in JobStateMachine.TERMINAL_STATES:
            from app.services.supervisor_service import supervisor_service
            await supervisor_service.fail(
                db, job_uuid, reason=reason, correlation_id=state.get("correlation_id")
            )
    return {
        "status": JobStatus.FAILED.value,
        "blocking_reason": reason,
        "events": [{"type": "ESCALATION_RECORDED", "reason": reason}],
    }'''

new_escalation = '''async def node_handle_escalation(state: SupervisorLoopState) -> dict:
    """15. Halts workflow and records auditable escalation without prematurely failing job."""
    reason = state.get("blocking_reason") or "Workflow escalated due to policy violation or unrecoverable error."
    job_uuid = UUID(state["job_id"])
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_uuid)
        if job and JobStatus(job.status) not in JobStateMachine.TERMINAL_STATES:
            from app.models.audit import AuditEvent
            job.blocking_reason = reason
            job.active_node = "escalation"
            db.add(AuditEvent(
                job_id=job.job_id,
                event_type="WORKFLOW_ESCALATED",
                actor_type="SYSTEM",
                actor_id="supervisor",
                correlation_id=state.get("correlation_id"),
                payload={"reason": reason, "current_status": job.status},
            ))
            await db.commit()
    return {
        "status": state.get("status", JobStatus.PAUSED.value),
        "blocking_reason": reason,
        "events": [{"type": "ESCALATION_RECORDED", "reason": reason}],
    }'''

assert old_escalation in content, "old_escalation not found!"
content = content.replace(old_escalation, new_escalation, 1)

# 3. Update build_supervisor_loop_graph to wire in AsyncPostgresSaver
old_build = '''def build_supervisor_loop_graph():
    """Builds the comprehensive multi-node deterministic supervisor LangGraph."""'''

new_build = '''def build_supervisor_loop_graph(checkpointer=None):
    """Builds the comprehensive multi-node deterministic supervisor LangGraph."""
    if checkpointer is None:
        from app.services.workflow_checkpointer import AsyncPostgresSaver
        checkpointer = AsyncPostgresSaver()'''

assert old_build in content, "old_build not found!"
content = content.replace(old_build, new_build, 1)

old_compile = "    return builder.compile()"
new_compile = "    return builder.compile(checkpointer=checkpointer, interrupt_before=['pause_for_human'])"

assert old_compile in content, "old_compile not found!"
content = content.replace(old_compile, new_compile, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully updated supervisor_graph.py!")

