"""Legacy Analyzer Orchestrator: Coordinates parallel workers, reconciles findings, and builds LegacyModel."""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.phase4 import (
    AnalysisConflictRecord,
    AnalysisEvidenceRecord,
    AnalysisRunModel,
    AnalysisWorkerModel,
    LegacyModelRecord,
    RepositorySnapshotModel,
)
from app.models.user import User
from app.schemas.phase4 import (
    AnalysisConflict,
    AnalysisType,
    AnalyzerWorkerResult,
    ArchitecturalRisk,
    ConfidenceLevel,
    ConfigurationItem,
    DependencyEdge,
    EvidenceRef,
    LegacyModel,
    LegacyModule,
    LegacyTestSuite,
    PersistenceEntity,
    PublicInterface,
    RepositoryInventory,
    RepositorySnapshot,
    WorkerLifecycleStatus,
)
from app.services.analyzer_workers import (
    ConfigurationWorker,
    DependenciesWorker,
    IntegrationExternalWorker,
    PersistenceWorker,
    PublicInterfacesWorker,
    RiskSecurityWorker,
    StructureModulesWorker,
    TestsWorker,
)
from app.services.artifact_service import ArtifactService
from app.services.evidence_service import evidence_service

logger = logging.getLogger(__name__)


class AnalyzerCoordinator:
    """Coordinates parallel specialized analyzer workers, reconciles findings, and builds LegacyModel."""

    def __init__(self, artifact_service: Optional[ArtifactService] = None):
        try:
            self.artifact_service = artifact_service or ArtifactService()
            self.workers = {
                AnalysisType.STRUCTURE_MODULES: StructureModulesWorker(),
                AnalysisType.DEPENDENCIES: DependenciesWorker(),
                AnalysisType.PUBLIC_INTERFACES: PublicInterfacesWorker(),
                AnalysisType.PERSISTENCE_DATA: PersistenceWorker(),
                AnalysisType.CONFIGURATION: ConfigurationWorker(),
                AnalysisType.TESTS: TestsWorker(),
                AnalysisType.INTEGRATION_EXTERNAL: IntegrationExternalWorker(),
                AnalysisType.RISK_SECURITY: RiskSecurityWorker(),
            }
        except Exception as exc:
            logger.exception("AnalyzerCoordinator init failed | %s: %s", type(exc).__name__, exc)
            raise

    async def run_worker_async(
        self,
        worker_type: AnalysisType,
        workspace_path: Path,
        inventory: RepositoryInventory,
    ) -> AnalyzerWorkerResult:
        """Run a worker slice in a separate thread to maintain non-blocking async execution."""
        try:
            worker = self.workers[worker_type]
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, worker.run_slice, workspace_path, inventory, None)
            return result
        except Exception as exc:
            logger.exception("run_worker_async failed | worker=%s | %s: %s", worker_type, type(exc).__name__, exc)
            return AnalyzerWorkerResult(
                worker_id=f"worker_err_{uuid.uuid4().hex[:8]}",
                analysis_type=worker_type,
                status=WorkerLifecycleStatus.FAILED,
                errors=[str(exc)],
                confidence=ConfidenceLevel.UNKNOWN,
            )

    def reconcile_and_merge(
        self,
        worker_results: List[AnalyzerWorkerResult],
        job_id: str,
        snapshot_id: str,
        version: int = 1,
    ) -> Tuple[LegacyModel, List[AnalysisConflict], Dict[str, EvidenceRef]]:
        """Deterministically merges worker findings, detects contradictions/conflicts, and produces LegacyModel."""
        try:
            evidence_index: Dict[str, EvidenceRef] = {}
            conflicts: List[AnalysisConflict] = []

            # Populate evidence index from all workers
            for wr in worker_results:
                for ev in wr.evidence:
                    evidence_index[ev.evidence_id] = ev

            modules: List[LegacyModule] = []
            dependencies: List[DependencyEdge] = []
            interfaces: List[PublicInterface] = []
            entities: List[PersistenceEntity] = []
            configs: List[ConfigurationItem] = []
            test_suites: List[LegacyTestSuite] = []
            risks: List[ArchitecturalRisk] = []

            # Extract from specific worker findings
            for wr in worker_results:
                if wr.analysis_type == AnalysisType.STRUCTURE_MODULES:
                    raw_mods = wr.findings.get("modules", [])
                    for rm in raw_mods:
                        modules.append(LegacyModule(
                            module_id=rm["module_id"],
                            path=rm["path"],
                            responsibility=rm["responsibility"],
                            language=rm["language"],
                            entry_points=rm.get("entry_points", []),
                            public_interfaces=[],
                            dependencies=[],
                            dependents=[],
                            configuration_dependencies=[],
                            risk="MEDIUM",
                            confidence=ConfidenceLevel.CONFIRMED,
                            evidence_refs=rm.get("evidence_refs", []),
                        ))
                elif wr.analysis_type == AnalysisType.DEPENDENCIES:
                    raw_deps = wr.findings.get("dependencies", [])
                    for rd in raw_deps:
                        dependencies.append(DependencyEdge(
                            source=rd["source"],
                            target=rd["target"],
                            dependency_type=rd.get("dependency_type", "CODE_IMPORT"),
                            evidence=rd.get("evidence", []),
                            confidence=ConfidenceLevel.CONFIRMED,
                        ))
                elif wr.analysis_type == AnalysisType.PUBLIC_INTERFACES:
                    raw_ifaces = wr.findings.get("public_interfaces", [])
                    for rif in raw_ifaces:
                        interfaces.append(PublicInterface(
                            interface_id=rif["interface_id"],
                            interface_type=rif["interface_type"],
                            name=rif["name"],
                            signature=rif.get("signature"),
                            location_path=rif["location_path"],
                            line_number=rif.get("line_number"),
                            consumer_modules=[],
                            evidence_refs=rif.get("evidence_refs", []),
                        ))
                elif wr.analysis_type == AnalysisType.PERSISTENCE_DATA:
                    raw_ents = wr.findings.get("persistence_entities", [])
                    for re_item in raw_ents:
                        entities.append(PersistenceEntity(
                            entity_id=re_item["entity_id"],
                            name=re_item["name"],
                            entity_type=re_item["entity_type"],
                            database_engine=re_item.get("database_engine"),
                            source_path=re_item["source_path"],
                            evidence_refs=re_item.get("evidence_refs", []),
                        ))
                elif wr.analysis_type == AnalysisType.CONFIGURATION:
                    raw_cfgs = wr.findings.get("configurations", [])
                    for rc in raw_cfgs:
                        configs.append(ConfigurationItem(
                            config_key=rc["config_key"],
                            config_type=rc["config_type"],
                            source_file=rc["source_file"],
                            default_value=rc.get("default_value"),
                            secret_reference_detected=rc.get("secret_reference_detected", False),
                            evidence_refs=rc.get("evidence_refs", []),
                        ))
                elif wr.analysis_type == AnalysisType.TESTS:
                    raw_ts = wr.findings.get("test_suites", [])
                    for rt in raw_ts:
                        test_suites.append(LegacyTestSuite(
                            suite_id=rt["suite_id"],
                            framework=rt["framework"],
                            test_location=rt["test_location"],
                            test_count=rt.get("test_count", 0),
                            test_type=rt.get("test_type", "UNIT"),
                            covered_modules=[],
                            evidence_refs=rt.get("evidence_refs", []),
                        ))
                elif wr.analysis_type == AnalysisType.RISK_SECURITY:
                    raw_risks = wr.findings.get("risks", [])
                    for rr in raw_risks:
                        risks.append(ArchitecturalRisk(
                            risk_id=rr["risk_id"],
                            category=rr["category"],
                            title=rr["title"],
                            description=rr["description"],
                            severity=rr["severity"],
                            inferred=rr.get("inferred", False),
                            evidence_refs=rr.get("evidence_refs", []),
                            mitigation_suggestion=rr.get("mitigation_suggestion"),
                        ))

            # Contradiction / Conflict Detection:
            # Check if multiple entities claim different database engines or conflicting module boundaries
            db_engines = {e.database_engine for e in entities if e.database_engine}
            if len(db_engines) > 1 and "SQL" in db_engines and "Relational" in db_engines:
                # Mergeable without conflict
                pass
            elif len(db_engines) > 1:
                # Create an explicit conflict
                conf = AnalysisConflict(
                    conflict_id=f"conf_{uuid.uuid4().hex[:8]}",
                    subject="Database Engine Ambiguity",
                    claim_a=f"Discovered engine '{list(db_engines)[0]}'",
                    claim_b=f"Discovered engine '{list(db_engines)[1]}'",
                    confidence_a=ConfidenceLevel.INFERRED,
                    confidence_b=ConfidenceLevel.INFERRED,
                    resolution_status="UNRESOLVED",
                    resolution_notes="Discrepancy detected between multiple persistence entity declarations.",
                )
                conflicts.append(conf)

            # Compute canonical model hash
            hasher = hashlib.sha256()
            hasher.update(json.dumps([m.model_dump() for m in modules], sort_keys=True).encode("utf-8"))
            hasher.update(json.dumps([i.model_dump() for i in interfaces], sort_keys=True).encode("utf-8"))
            hasher.update(json.dumps([e.model_dump() for e in entities], sort_keys=True).encode("utf-8"))
            content_hash = hasher.hexdigest()

            legacy_model = LegacyModel(
                model_id=f"legacy_{uuid.uuid4().hex[:12]}",
                job_id=job_id,
                snapshot_id=snapshot_id,
                version=version,
                modules=modules,
                dependency_graph=dependencies,
                public_interfaces=interfaces,
                persistence_entities=entities,
                configurations=configs,
                test_suites=test_suites,
                risks=risks,
                conflicts=conflicts,
                evidence_index=evidence_index,
                content_hash=content_hash,
            )
            return legacy_model, conflicts, evidence_index
        except Exception as exc:
            logger.exception("reconcile_and_merge failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    def analyze_repository(
        self,
        job_id: str,
        snapshot_id: str,
        workspace_path: Any,
        file_items: List[Any],
    ) -> LegacyModel:
        """Synchronously execute all 8 worker slices and reconcile into canonical LegacyModel."""
        try:
            if isinstance(file_items, RepositoryInventory):
                inventory = file_items
            else:
                inventory = RepositoryInventory(
                    inventory_id=f"inv_{snapshot_id}",
                    snapshot_id=snapshot_id,
                    job_id=job_id,
                    total_files=len(file_items),
                    total_bytes=sum(getattr(f, "size_bytes", 0) for f in file_items),
                    files=file_items,
                    directories=[],
                    inventory_hash="hash",
                )
            ws_path = Path(workspace_path)
            results = [w.run_slice(ws_path, inventory, None) for w in self.workers.values()]
            legacy_model, conflicts, evidence_index = self.reconcile_and_merge(
                results, job_id, snapshot_id
            )
            return legacy_model
        except Exception as exc:
            logger.exception("analyze_repository failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    def reconcile_conflicts(
        self,
        modules: List[Any],
        detected_architecture: str,
        inferred_framework: str,
        framework_claims: List[Dict[str, Any]],
    ) -> List[AnalysisConflict]:
        """Detect and surface conflicts when worker claims disagree."""
        conflicts = []
        if len(framework_claims) > 1:
            claims = [fc["framework"] for fc in framework_claims]
            if len(set(claims)) > 1:
                conflicts.append(AnalysisConflict(
                    conflict_id=f"conf_{uuid.uuid4().hex[:12]}",
                    subject="primary_framework",
                    claim_a=framework_claims[0]["framework"],
                    claim_b=framework_claims[1]["framework"],
                    evidence_a=[framework_claims[0].get("evidence", "ev_a")],
                    evidence_b=[framework_claims[1].get("evidence", "ev_b")],
                    resolution_status="UNRESOLVED",
                ))
        return conflicts

    async def execute_analysis(
        self,
        db: AsyncSession,
        job: Job,
        snapshot: RepositorySnapshot,
        inventory: RepositoryInventory,
        workspace_path: Path,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
        slices_to_run: Optional[List[AnalysisType]] = None,
    ) -> LegacyModel:
        """Executes full analysis workflow across all specialized worker slices and persists canonical LegacyModel."""
        try:
            job_id_str = str(job.job_id)
            slices = slices_to_run or list(self.workers.keys())

            # Check existing latest version for increment
            existing_model = (
                await db.execute(
                    select(LegacyModelRecord)
                    .where(LegacyModelRecord.job_id == job.job_id)
                    .order_by(LegacyModelRecord.version.desc())
                )
            ).scalars().first()
            next_version = 1 if not existing_model else existing_model.version + 1

            run_id = uuid.uuid4()
            db_run = AnalysisRunModel(
                run_id=run_id,
                job_id=job.job_id,
                snapshot_id=uuid.UUID(snapshot.snapshot_id),
                version=next_version,
                status="RUNNING",
            )
            db.add(db_run)
            await db.flush()

            # Execute workers in parallel
            tasks = [self.run_worker_async(wt, workspace_path, inventory) for wt in slices]
            worker_results: List[AnalyzerWorkerResult] = await asyncio.gather(*tasks)

            # Persist worker outputs
            for wr in worker_results:
                db_worker = AnalysisWorkerModel(
                    worker_id=uuid.UUID(wr.worker_id.replace("worker_", "").replace("struct_", "").replace("dep_", "").replace("iface_", "").replace("persist_", "").replace("cfg_", "").replace("test_", "").replace("integ_", "").replace("risk_", "").replace("err_", "").ljust(32, "0")[:32]) if len(wr.worker_id) == 36 else uuid.uuid4(),
                    run_id=run_id,
                    job_id=job.job_id,
                    analysis_type=wr.analysis_type.value,
                    status=wr.status.value,
                    input_scope=wr.input_scope,
                    findings=wr.findings,
                    confidence=wr.confidence.value,
                    warnings=wr.warnings,
                    errors=wr.errors,
                    model_version=wr.model_version,
                    prompt_version=wr.prompt_version,
                    artifact_hash=wr.artifact_hash,
                )
                db.add(db_worker)

            # Reconcile findings
            legacy_model, conflicts, evidence_index = self.reconcile_and_merge(
                worker_results=worker_results,
                job_id=job_id_str,
                snapshot_id=snapshot.snapshot_id,
                version=next_version,
            )

            # Persist evidence records
            for ev in evidence_index.values():
                db.add(AnalysisEvidenceRecord(
                    evidence_id=uuid.uuid4(),
                    job_id=job.job_id,
                    source_artifact=ev.source_artifact,
                    source_path=ev.source_path,
                    source_location=ev.source_location,
                    evidence_type=ev.evidence_type.value,
                    evidence_excerpt=ev.evidence_excerpt,
                    content_hash=ev.content_hash,
                    confidence=ev.confidence.value,
                    agent_name=ev.agent_name,
                    artifact_version=ev.artifact_version,
                ))

            # Persist conflict records
            for conf in conflicts:
                db.add(AnalysisConflictRecord(
                    conflict_id=uuid.uuid4(),
                    job_id=job.job_id,
                    subject=conf.subject,
                    claim_a=conf.claim_a,
                    claim_b=conf.claim_b,
                    evidence_a=conf.evidence_a,
                    evidence_b=conf.evidence_b,
                    confidence_a=conf.confidence_a.value,
                    confidence_b=conf.confidence_b.value,
                    resolution_status=conf.resolution_status,
                    resolution_notes=conf.resolution_notes,
                ))

            # Persist LegacyModel record
            db_legacy = LegacyModelRecord(
                model_id=uuid.UUID(legacy_model.model_id.replace("legacy_", "").ljust(32, "0")[:32]) if len(legacy_model.model_id) == 36 else uuid.uuid4(),
                job_id=job.job_id,
                version=next_version,
                snapshot_id=uuid.UUID(snapshot.snapshot_id),
                modules_payload=[m.model_dump() for m in legacy_model.modules],
                dependencies_payload=[d.model_dump() for d in legacy_model.dependency_graph],
                interfaces_payload=[i.model_dump() for i in legacy_model.public_interfaces],
                persistence_payload=[p.model_dump() for p in legacy_model.persistence_entities],
                configurations_payload=[c.model_dump() for c in legacy_model.configurations],
                tests_payload=[t.model_dump() for t in legacy_model.test_suites],
                risks_payload=[r.model_dump() for r in legacy_model.risks],
                conflicts_payload=[cf.model_dump(mode="json") for cf in legacy_model.conflicts],
                content_hash=legacy_model.content_hash,
            )
            db.add(db_legacy)

            db_run.status = "COMPLETED"
            db_run.completed_at = legacy_model.created_at

            # Publish LegacyModel artifact
            await self.artifact_service.create_artifact(
                db=db,
                job_id=job.job_id,
                artifact_type="LegacyModel",
                version=next_version,
                content_bytes=json.dumps(legacy_model.model_dump(mode="json"), indent=2).encode("utf-8"),
                producing_agent="LegacyAnalyzerCoordinator",
                derived_from=[snapshot.content_hash],
                user=user,
                correlation_id=correlation_id,
            )

            await db.commit()
            return legacy_model
        except Exception as exc:
            logger.exception("execute_analysis failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise


analyzer_coordinator = AnalyzerCoordinator()
