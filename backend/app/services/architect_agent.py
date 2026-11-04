"""Architect Agent: Synthesizes LegacyModel and target requirements into a versioned TargetBlueprint."""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.base import utc_now
from app.models.phase4 import TargetBlueprintModel
from app.models.user import User
from app.schemas.phase4 import (
    BlueprintStatus,
    LegacyModel,
    TargetBlueprint,
    TargetComponent,
    TargetDataModel,
    TargetInterfaceContract,
)
from app.services.artifact_service import ArtifactService

logger = logging.getLogger(__name__)


class ArchitectAgent:
    """Specialist Agent mapping legacy capabilities to target modular architectures without generating code."""

    def __init__(self, artifact_service: Optional[ArtifactService] = None):
        try:
            self.artifact_service = artifact_service or ArtifactService()
        except Exception as exc:
            logger.exception("ArchitectAgent init failed | %s: %s", type(exc).__name__, exc)
            raise

    def create_blueprint(
        self,
        legacy_model: LegacyModel,
        target_stack: str,
        target_architecture: str = "Modular Clean Architecture / Hexagonal",
        job_id: Optional[str] = None,
        version: int = 1,
        project_constraints: Optional[List[str]] = None,
        constraints: Optional[str] = None,
        accepted_decisions: Optional[List[Dict[str, Any]]] = None,
    ) -> TargetBlueprint:
        """Convenience method accepting keyword arguments and legacy model."""
        jid = job_id or getattr(legacy_model, "job_id", "job_blueprint")
        c_str = constraints or ("\n".join(project_constraints) if project_constraints else None)
        return self.generate_blueprint(
            job_id=jid,
            legacy_model=legacy_model,
            target_stack=target_stack,
            target_architecture=target_architecture,
            version=version,
            constraints=c_str,
            accepted_decisions=accepted_decisions,
        )

    def generate_blueprint(
        self,
        job_id: str,
        legacy_model: LegacyModel,
        target_stack: str,
        target_architecture: str = "Modular Clean Architecture / Hexagonal",
        version: int = 1,
        constraints: Optional[str] = None,
        accepted_decisions: Optional[List[Dict[str, Any]]] = None,
    ) -> TargetBlueprint:
        """Deterministically maps LegacyModel capabilities to target components and contracts."""
        try:
            target_components: List[TargetComponent] = []
            target_interfaces: List[TargetInterfaceContract] = []
            target_data_models: List[TargetDataModel] = []

            # 1. Map legacy modules to target components
            for mod in legacy_model.modules:
                clean_name = getattr(mod, "name", None) or mod.module_id.replace("mod_", "").replace("module_", "")
                comp_id = f"comp_{clean_name}"
                target_path = f"src/modules/{clean_name}" if target_stack.startswith("TypeScript") else f"app/modules/{clean_name}"

                target_components.append(TargetComponent(
                    component_id=comp_id,
                    name=f"target-{clean_name}",
                    target_path=target_path,
                    mapped_legacy_modules=[mod.module_id],
                    responsibilities=[mod.responsibility, "Domain Service & Entity Orchestration"],
                    technologies=[target_stack.split("/")[0].strip()],
                    dependencies=[],
                    interfaces=[iface.interface_id for iface in legacy_model.public_interfaces if iface.location_path.startswith(mod.path)],
                ))

            # 2. Map legacy public interfaces to target contracts
            for iface in legacy_model.public_interfaces:
                contract_id = f"contract_{iface.interface_id.replace('iface_', '')}"
                target_interfaces.append(TargetInterfaceContract(
                    contract_id=contract_id,
                    component_id=target_components[0].component_id if target_components else "comp_root",
                    interface_type="REST_API" if iface.interface_type == "REST_ENDPOINT" else "INTERNAL_SERVICE",
                    name=iface.name,
                    specification={"legacy_signature": iface.signature, "path": iface.location_path},
                    preserved_legacy_interface_id=iface.interface_id,
                ))

            # 3. Map legacy persistence entities to target data model
            for entity in legacy_model.persistence_entities:
                target_data_models.append(TargetDataModel(
                    model_id=f"model_{entity.entity_id.replace('entity_', '')}",
                    name=entity.name,
                    orm_strategy="Prisma / TypeORM" if "TypeScript" in target_stack else "SQLAlchemy / Alembic",
                    target_engine=entity.database_engine or "PostgreSQL",
                    schema_definition={"table": entity.name, "entity_type": entity.entity_type},
                    migration_strategy="Automated Schema DDL & Versioned Migrations",
                    mapped_legacy_entities=[entity.entity_id],
                ))

            # Constraints and security rules
            sec_constraints = [
                "Zero secret leakage in repository source and logs",
                "Default-deny network egress for converted runtime modules",
                "Explicit session authentication and RBAC guards on all public controllers",
            ]
            compat_constraints = [
                "Behavioral equivalence preservation for all public REST API endpoints",
                "Status codes, response schema fields, and error codes must match legacy contracts",
            ]
            mig_constraints = [
                "Independent module conversion waves respecting topological dependency order",
                "Zero downtime cutover with legacy adapter fallback during transition",
            ]

            # Content hash
            hasher = hashlib.sha256()
            hasher.update(json.dumps([c.model_dump() for c in target_components], sort_keys=True).encode("utf-8"))
            hasher.update(json.dumps([i.model_dump() for i in target_interfaces], sort_keys=True).encode("utf-8"))
            hasher.update(json.dumps([d.model_dump() for d in target_data_models], sort_keys=True).encode("utf-8"))
            content_hash = hasher.hexdigest()

            blueprint = TargetBlueprint(
                blueprint_id=f"bp_{uuid.uuid4().hex[:12]}",
                job_id=job_id,
                version=version,
                status=BlueprintStatus.UNDER_REVIEW,
                target_stack=target_stack,
                target_architecture=target_architecture,
                components=target_components,
                interfaces=target_interfaces,
                data_model=target_data_models,
                integration_contracts=[],
                deployment_constraints=["Containerized execution with non-root user"],
                security_constraints=sec_constraints,
                compatibility_constraints=compat_constraints,
                migration_constraints=mig_constraints,
                accepted_decisions=accepted_decisions or [],
                open_constraints=[constraints] if constraints else [],
                evidence_refs=[ev_id for ev_id in legacy_model.evidence_index.keys()][:50],
                created_by="ArchitectAgent",
                content_hash=content_hash,
            )
            return blueprint
        except Exception as exc:
            logger.exception("generate_blueprint failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    async def execute_architect(
        self,
        db: AsyncSession,
        job: Job,
        legacy_model: LegacyModel,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
        constraints_override: Optional[str] = None,
        accepted_decisions: Optional[List[Dict[str, Any]]] = None,
    ) -> TargetBlueprint:
        """Executes architect agent synthesis, records TargetBlueprint in DB, and publishes artifact."""
        try:
            job_id_str = str(job.job_id)

            # Determine next version
            existing_bp = (
                await db.execute(
                    select(TargetBlueprintModel)
                    .where(TargetBlueprintModel.job_id == job.job_id)
                    .order_by(TargetBlueprintModel.version.desc())
                )
            ).scalars().first()
            next_version = 1 if not existing_bp else existing_bp.version + 1

            blueprint = self.generate_blueprint(
                job_id=job_id_str,
                legacy_model=legacy_model,
                target_stack=job.target_stack,
                version=next_version,
                constraints=constraints_override or job.description,
                accepted_decisions=accepted_decisions,
            )

            # FLOW-04: Record distinct AgentRun for Architect specialist
            run_uuid = uuid.uuid4()
            architect_run = AgentRun(
                run_id=run_uuid,
                job_id=job.job_id,
                task_id=f"task_architect_{job.job_id}_{next_version}",
                correlation_id=correlation_id or uuid.uuid4().hex,
                agent_name="Architect",
                model_provider="internal",
                model_identifier="architect-agent-v1",
                status="COMPLETED",
                input_tokens=150,
                output_tokens=300,
                cost_usd=0.005,
                reported_input_tokens=150,
                reported_output_tokens=300,
                provider_model_id="architect-agent-v1",
                estimated_cost=0.005,
                billed_cost=None,
                started_at=utc_now(),
                completed_at=utc_now(),
                task_payload={"agent_name": "Architect", "action": "generate_blueprint", "version": next_version},
                output_payload={"blueprint_version": next_version},
            )
            db.add(architect_run)
            await db.flush()

            # Persist blueprint record
            db_bp = TargetBlueprintModel(
                blueprint_id=uuid.UUID(blueprint.blueprint_id.replace("bp_", "").ljust(32, "0")[:32]) if len(blueprint.blueprint_id) == 35 else uuid.uuid4(),
                job_id=job.job_id,
                version=next_version,
                status=blueprint.status.value,
                target_stack=blueprint.target_stack,
                target_architecture=blueprint.target_architecture,
                components_payload=[c.model_dump() for c in blueprint.components],
                interfaces_payload=[i.model_dump() for i in blueprint.interfaces],
                data_model_payload=[d.model_dump() for d in blueprint.data_model],
                integration_contracts_payload=blueprint.integration_contracts,
                constraints_payload={
                    "deployment": blueprint.deployment_constraints,
                    "security": blueprint.security_constraints,
                    "compatibility": blueprint.compatibility_constraints,
                    "migration": blueprint.migration_constraints,
                    "open": blueprint.open_constraints,
                },
                accepted_decisions=blueprint.accepted_decisions,
                evidence_refs=blueprint.evidence_refs,
                created_by="ArchitectAgent",
                content_hash=blueprint.content_hash,
            )
            db.add(db_bp)

            # Publish artifact linked to producer AgentRun
            legacy_art = (
                await db.execute(
                    select(Artifact)
                    .where(
                        Artifact.job_id == job.job_id,
                        Artifact.artifact_type == "LegacyModel",
                    )
                    .order_by(Artifact.version.desc())
                )
            ).scalars().first()
            lineage = [str(legacy_art.artifact_id)] if legacy_art else []

            art = await self.artifact_service.create_artifact(
                db=db,
                job_id=job.job_id,
                artifact_type="TargetBlueprint",
                version=next_version,
                content_bytes=json.dumps(blueprint.model_dump(mode="json"), indent=2).encode("utf-8"),
                producing_agent="ArchitectAgent",
                derived_from=lineage,
                user=user,
                correlation_id=correlation_id,
                producer_run_id=architect_run.run_id,
            )
            blueprint.content_hash = art.content_hash

            await db.commit()
            return blueprint
        except Exception as exc:
            logger.exception("execute_architect failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise


architect_agent = ArchitectAgent()
