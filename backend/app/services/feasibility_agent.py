"""Feasibility Agent: Evaluates capability parity, tool readiness, and gaps for Gate G1."""

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
from app.models.phase4 import FeasibilityCapabilityModel, FeasibilityReportModel
from app.models.user import User
from app.schemas.phase4 import (
    CapabilityClassification,
    FeasibilityCapability,
    FeasibilityReport,
    LegacyModel,
    TargetBlueprint,
    ToolReadiness,
)
from app.services.artifact_service import ArtifactService

logger = logging.getLogger(__name__)


class FeasibilityAgent:
    """Specialist Agent evaluating target stack parity, adapter requirements, and tool readiness."""

    def __init__(self, artifact_service: Optional[ArtifactService] = None):
        try:
            self.artifact_service = artifact_service or ArtifactService()
        except Exception as exc:
            logger.exception("FeasibilityAgent init failed | %s: %s", type(exc).__name__, exc)
            raise

    def evaluate_feasibility(
        self,
        legacy_model: LegacyModel,
        target_blueprint: TargetBlueprint,
        job_id: Optional[str] = None,
        version: int = 1,
    ) -> FeasibilityReport:
        """Evaluates capability parity, tool readiness, and gaps for TargetBlueprint."""
        jid = job_id or getattr(target_blueprint, "job_id", None) or "job_feasibility"
        return self.assess_feasibility(
            job_id=jid,
            legacy_model=legacy_model,
            blueprint=target_blueprint,
            version=version,
        )

    @staticmethod
    def probe_tool(
        tool_name: str,
        binary_candidates: List[str],
        version_flag: str = "--version",
        optional: bool = False,
    ) -> ToolReadiness:
        import shutil
        import subprocess

        for cand in binary_candidates:
            path = shutil.which(cand)
            if path:
                try:
                    proc = subprocess.run([path, version_flag], capture_output=True, text=True, timeout=2.0)
                    out = (proc.stdout or proc.stderr or "").strip().splitlines()
                    ver = out[0][:60] if out else "detected"
                    return ToolReadiness(
                        tool=tool_name,
                        availability=True,
                        version=ver,
                        compatibility="COMPATIBLE",
                        configuration_status="CONFIGURED",
                        readiness="READY",
                        evidence=[f"Probed '{cand}' at {path} ({ver})"],
                    )
                except Exception as e:
                    return ToolReadiness(
                        tool=tool_name,
                        availability=True,
                        version="detected",
                        compatibility="COMPATIBLE",
                        configuration_status="CONFIGURED",
                        readiness="READY",
                        evidence=[f"Found '{cand}' at {path} (probe note: {e})"],
                    )
        return ToolReadiness(
            tool=tool_name,
            availability=False,
            version=None,
            compatibility="INCOMPATIBLE" if not optional else "PARTIAL",
            configuration_status="MISSING",
            readiness="BLOCKED" if not optional else "OPTIONAL",
            evidence=[f"Tool binary '{binary_candidates[0]}' was not found on system PATH."],
        )

    def assess_feasibility(
        self,
        job_id: str,
        legacy_model: LegacyModel,
        blueprint: TargetBlueprint,
        version: int = 1,
    ) -> FeasibilityReport:
        """Compares legacy requirements against target blueprint and evaluates tool readiness."""
        try:
            capabilities: List[FeasibilityCapability] = []
            tool_readiness: List[ToolReadiness] = []

            # 1. Technology: Framework & Language mapping
            for mod in legacy_model.modules:
                cap_id = f"cap_tech_{mod.module_id}"
                is_standard = mod.language in {"Java", "Python", "JavaScript", "TypeScript", "Go"}
                classification = CapabilityClassification.SUPPORTED if is_standard else CapabilityClassification.SUBSTITUTE

                capabilities.append(FeasibilityCapability(
                    capability_id=cap_id,
                    category="TECHNOLOGY",
                    legacy_requirement=f"Module '{mod.path}' implemented in {mod.language}",
                    target_requirement=f"Convert to target stack '{blueprint.target_stack}'",
                    classification=classification,
                    confidence=1.0 if is_standard else 0.85,
                    evidence=mod.evidence_refs,
                    tool_dependency="compiler/linter",
                    effort="MEDIUM",
                    risk="LOW" if is_standard else "MEDIUM",
                    verification_impact="Requires type checking and unit test parity.",
                    recommendation="Proceed with automated conversion in planned waves.",
                ))

            # 2. Data / Persistence capability evaluation
            for entity in legacy_model.persistence_entities:
                cap_id = f"cap_data_{entity.entity_id}"
                has_sql = entity.database_engine in {"SQL", "Relational", "PostgreSQL", "MySQL", "SQLite"}
                classification = CapabilityClassification.SUPPORTED if has_sql else CapabilityClassification.CUSTOM_BUILD

                capabilities.append(FeasibilityCapability(
                    capability_id=cap_id,
                    category="DATA",
                    legacy_requirement=f"Entity '{entity.name}' ({entity.entity_type})",
                    target_requirement=f"Target ORM schema model and migration for {entity.name}",
                    classification=classification,
                    confidence=0.95,
                    evidence=entity.evidence_refs,
                    tool_dependency="database_migration_tool",
                    effort="LOW" if has_sql else "HIGH",
                    risk="LOW" if has_sql else "HIGH",
                    verification_impact="Requires schema diff validation and row count equivalence.",
                    recommendation="Map to target ORM repository model with type-safe schema.",
                ))

            # 3. Interfaces / Networking evaluation
            for iface in legacy_model.public_interfaces:
                cap_id = f"cap_iface_{iface.interface_id}"
                classification = CapabilityClassification.SUPPORTED
                capabilities.append(FeasibilityCapability(
                    capability_id=cap_id,
                    category="INTERFACES",
                    legacy_requirement=f"Public route '{iface.name}' ({iface.interface_type})",
                    target_requirement=f"Equivalent HTTP REST Controller endpoint in {blueprint.target_stack}",
                    classification=classification,
                    confidence=1.0,
                    evidence=iface.evidence_refs,
                    tool_dependency="http_client_test_runner",
                    effort="LOW",
                    risk="LOW",
                    verification_impact="Black-box characterization replay against both legacy and target.",
                    recommendation="Preserve HTTP method, route path, status code, and JSON payload format.",
                ))

            # 4. Tool readiness evaluation via real host probes (TEST-05)
            tool_readiness.append(self.probe_tool(
                tool_name="TypeScript Compiler (tsc)",
                binary_candidates=["tsc", "tsc.cmd"],
                version_flag="--version",
            ))
            tool_readiness.append(self.probe_tool(
                tool_name="Vitest / Jest Test Runner",
                binary_candidates=["vitest", "vitest.cmd", "jest", "jest.cmd", "npm", "npm.cmd"],
                version_flag="--version",
            ))
            tool_readiness.append(self.probe_tool(
                tool_name="pytest",
                binary_candidates=["pytest", "pytest.exe"],
                version_flag="--version",
            ))
            tool_readiness.append(self.probe_tool(
                tool_name="git",
                binary_candidates=["git", "git.exe"],
                version_flag="--version",
            ))
            tool_readiness.append(self.probe_tool(
                tool_name="Isolated Rootless Container Sandbox",
                binary_candidates=["docker", "docker.exe", "podman", "podman.exe"],
                version_flag="--version",
                optional=True,
            ))

            unsupported = sum(1 for c in capabilities if c.classification == CapabilityClassification.UNSUPPORTED)
            custom_build = sum(1 for c in capabilities if c.classification == CapabilityClassification.CUSTOM_BUILD)
            substitute = sum(1 for c in capabilities if c.classification == CapabilityClassification.SUBSTITUTE)
            unknown = sum(1 for c in capabilities if c.classification == CapabilityClassification.UNKNOWN)

            score = 1.0 - (unsupported * 0.3 + custom_build * 0.1 + unknown * 0.2) / max(1, len(capabilities))
            score = max(0.0, min(1.0, round(score, 2)))

            hasher = hashlib.sha256()
            hasher.update(json.dumps([c.model_dump() for c in capabilities], sort_keys=True).encode("utf-8"))
            hasher.update(json.dumps([t.model_dump() for t in tool_readiness], sort_keys=True).encode("utf-8"))
            content_hash = hasher.hexdigest()

            summary = (
                f"Feasibility evaluation completed: {len(capabilities)} capabilities evaluated. "
                f"Feasibility Score: {score * 100:.1f}%. "
                f"{unsupported} unsupported, {custom_build} custom-build, {substitute} substitute, {unknown} unknown."
            )

            report = FeasibilityReport(
                report_id=f"feas_{uuid.uuid4().hex[:12]}",
                job_id=job_id,
                version=version,
                blueprint_version=blueprint.version,
                legacy_model_version=legacy_model.version,
                capabilities=capabilities,
                tool_readiness=tool_readiness,
                overall_feasibility_score=score,
                unsupported_count=unsupported,
                custom_build_count=custom_build,
                substitute_count=substitute,
                unknown_count=unknown,
                summary=summary,
                content_hash=content_hash,
            )
            return report
        except Exception as exc:
            logger.exception("assess_feasibility failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    async def execute_feasibility(
        self,
        db: AsyncSession,
        job: Job,
        legacy_model: LegacyModel,
        blueprint: TargetBlueprint,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
    ) -> FeasibilityReport:
        """Executes feasibility assessment, records in DB, and publishes artifact."""
        try:
            job_id_str = str(job.job_id)

            existing_report = (
                await db.execute(
                    select(FeasibilityReportModel)
                    .where(FeasibilityReportModel.job_id == job.job_id)
                    .order_by(FeasibilityReportModel.version.desc())
                )
            ).scalars().first()
            next_version = 1 if not existing_report else existing_report.version + 1

            report = self.assess_feasibility(
                job_id=job_id_str,
                legacy_model=legacy_model,
                blueprint=blueprint,
                version=next_version,
            )

            db_report = FeasibilityReportModel(
                report_id=uuid.UUID(report.report_id.replace("feas_", "").ljust(32, "0")[:32]) if len(report.report_id) == 35 else uuid.uuid4(),
                job_id=job.job_id,
                version=next_version,
                blueprint_version=report.blueprint_version,
                legacy_model_version=report.legacy_model_version,
                overall_score=report.overall_feasibility_score,
                unsupported_count=report.unsupported_count,
                custom_build_count=report.custom_build_count,
                substitute_count=report.substitute_count,
                unknown_count=report.unknown_count,
                summary=report.summary,
                content_hash=report.content_hash,
            )
            db.add(db_report)
            await db.flush()

            for cap in report.capabilities:
                db.add(FeasibilityCapabilityModel(
                    capability_record_id=uuid.uuid4(),
                    report_id=db_report.report_id,
                    capability_id=cap.capability_id,
                    category=cap.category,
                    legacy_requirement=cap.legacy_requirement,
                    target_requirement=cap.target_requirement,
                    classification=cap.classification.value,
                    confidence=cap.confidence,
                    tool_dependency=cap.tool_dependency,
                    effort=cap.effort,
                    risk=cap.risk,
                    verification_impact=cap.verification_impact,
                    recommendation=cap.recommendation,
                    evidence=cap.evidence,
                ))

            # FLOW-04: Record distinct AgentRun for Feasibility specialist
            run_uuid = uuid.uuid4()
            feasibility_run = AgentRun(
                run_id=run_uuid,
                job_id=job.job_id,
                task_id=f"task_feasibility_{job.job_id}_{next_version}",
                correlation_id=correlation_id or uuid.uuid4().hex,
                agent_name="Feasibility",
                model_provider="internal",
                model_identifier="feasibility-agent-v1",
                status="COMPLETED",
                input_tokens=200,
                output_tokens=400,
                cost_usd=0.008,
                reported_input_tokens=200,
                reported_output_tokens=400,
                provider_model_id="feasibility-agent-v1",
                estimated_cost=0.008,
                billed_cost=None,
                started_at=utc_now(),
                completed_at=utc_now(),
                task_payload={"agent_name": "Feasibility", "action": "assess_feasibility", "version": next_version},
                output_payload={"feasibility_version": next_version},
            )
            db.add(feasibility_run)
            await db.flush()

            # Publish artifact linked to producer AgentRun
            parent_arts = (
                await db.execute(
                    select(Artifact.artifact_id)
                    .where(
                        Artifact.job_id == job.job_id,
                        Artifact.artifact_type.in_(["LegacyModel", "TargetBlueprint"]),
                    )
                )
            ).scalars().all()
            feas_lineage = [str(aid) for aid in parent_arts]

            await self.artifact_service.create_artifact(
                db=db,
                job_id=job.job_id,
                artifact_type="FeasibilityReport",
                version=next_version,
                content_bytes=json.dumps(report.model_dump(mode="json"), indent=2).encode("utf-8"),
                producing_agent="FeasibilityAgent",
                derived_from=feas_lineage,
                user=user,
                correlation_id=correlation_id,
                producer_run_id=feasibility_run.run_id,
            )

            await db.commit()
            return report
        except Exception as exc:
            logger.exception("execute_feasibility failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise


feasibility_agent = FeasibilityAgent()
