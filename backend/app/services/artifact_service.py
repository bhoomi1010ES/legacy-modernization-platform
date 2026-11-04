"""Artifact versioning, cryptographic integrity validation, and lineage service."""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, ForbiddenException, NotFoundException, PlatformException
from app.core.storage import StorageAdapter, get_storage_adapter
from app.models.agent import AgentRun
from app.models.artifact import Artifact, ArtifactDependency, ArtifactType, normalize_artifact_type
from app.models.audit import AuditEvent
from app.models.base import utc_now
from app.models.user import User
from app.models.workflow import WorkflowGate, WorkflowOutbox

logger = logging.getLogger(__name__)

# Verification artifact types strictly reserved for Verifier specialist agents (SEC-07)
VERIFICATION_ARTIFACT_TYPES = {
    "VERIFICATIONREPORT",
    "EQUIVALENCEREPORT",
    "TESTRESULT",
    "SYSTEMVERIFICATION",
    "SYSTEMVERIFICATIONREPORT",
    "COVERAGEREPORT",
    "REVIEWREPORT",
}


class ArtifactService:
    """Manages immutable deliverable publishing, staged writes, and lineage tracking."""

    def __init__(self, storage_adapter: Optional[StorageAdapter] = None):
        self.storage = storage_adapter or get_storage_adapter()

    async def publish_artifact(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        artifact_type: str,
        version: int,
        content_bytes: bytes,
        producing_agent: str,
        derived_from: Optional[List[str]] = None,
        module_id: Optional[uuid.UUID] = None,
        media_type: str = "application/json",
        extra_metadata: Optional[Dict[str, Any]] = None,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
        producer_run_id: Optional[uuid.UUID] = None,
        schema_version: str = "1.0.0",
        commit: bool = True,
    ) -> Artifact:
        """Publishes an immutable artifact version using two-stage atomic storage protocol (DATA-07)."""
        canonical_type = normalize_artifact_type(artifact_type)

        # 1. Server-side privilege check: Verifier spoofing prevention (SEC-07)
        normalized_type = "".join(ch for ch in canonical_type.upper() if ch.isalnum())
        if normalized_type in VERIFICATION_ARTIFACT_TYPES:
            required_agent = "Reviewer" if normalized_type == "REVIEWREPORT" else "Verifier"
            if producing_agent != required_agent or producer_run_id is None:
                raise ForbiddenException(
                    f"Only {required_agent} agents with an independent persisted producer run may publish this evidence."
                )
            producer = await db.get(AgentRun, producer_run_id)
            if producer is None or producer.job_id != job_id or producer.agent_name != required_agent:
                raise ForbiddenException("Independent producer identity/job binding does not match")
            import json
            payload = json.loads(content_bytes)
            is_success = payload.get("passed") is True or payload.get("status") == "PASS"
            if is_success:
                from app.services.verification_proof import validate_success
                try:
                    validate_success(payload,producer,job_id,reviewer=required_agent=='Reviewer')
                except Exception as exc:
                    raise ForbiddenException("Successful verification requires authentic independent controller evidence") from exc

        # 2. Enforce uniqueness: an existing version must never be overwritten
        stmt = select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == canonical_type,
            Artifact.version == version,
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ConflictException(
                f"Artifact '{canonical_type}' version {version} already exists for this job. Artifacts are strictly immutable."
            )

        # 3. Validate producer_run_id if provided
        if producer_run_id:
            run_stmt = select(AgentRun).where(AgentRun.run_id == producer_run_id)
            run_res = await db.execute(run_stmt)
            run_record = run_res.scalar_one_or_none()
            if not run_record:
                raise PlatformException(
                    code="INVALID_PRODUCER_RUN",
                    message=f"AgentRun '{producer_run_id}' not found.",
                    status_code=400,
                )
            if run_record.job_id != job_id:
                raise PlatformException(
                    code="CROSS_JOB_LINEAGE_FORBIDDEN",
                    message=f"AgentRun '{producer_run_id}' belongs to job {run_record.job_id}, expected {job_id}.",
                    status_code=400,
                )

        # 4. Validate lineage & referential integrity via artifact_dependencies
        resolved_ancestor_artifacts: List[Artifact] = []
        if derived_from:
            for ref in derived_from:
                ref_str = str(ref).strip()
                if not ref_str:
                    continue

                # Query ancestor by artifact_id or content_hash
                target_uuid = None
                try:
                    target_uuid = uuid.UUID(ref_str)
                except ValueError:
                    pass

                if target_uuid:
                    # Query ancestor within same job first
                    anc_stmt = select(Artifact).where(
                        Artifact.job_id == job_id,
                        or_(Artifact.artifact_id == target_uuid, Artifact.content_hash == ref_str),
                    )
                    anc_res = await db.execute(anc_stmt)
                    ancestor = anc_res.scalars().first()
                    if not ancestor:
                        # Global lookup to detect cross-job lineage
                        anc_stmt_global = select(Artifact).where(
                            or_(Artifact.artifact_id == target_uuid, Artifact.content_hash == ref_str)
                        )
                        anc_res_global = await db.execute(anc_stmt_global)
                        ancestor = anc_res_global.scalars().first()
                else:
                    # Query ancestor within same job first
                    anc_stmt = select(Artifact).where(
                        Artifact.job_id == job_id,
                        Artifact.content_hash == ref_str,
                    )
                    anc_res = await db.execute(anc_stmt)
                    ancestor = anc_res.scalars().first()
                    if not ancestor:
                        # Global lookup to detect cross-job lineage
                        anc_stmt_global = select(Artifact).where(Artifact.content_hash == ref_str)
                        anc_res_global = await db.execute(anc_stmt_global)
                        ancestor = anc_res_global.scalars().first()

                if not ancestor:
                    # Model content_hash to Artifact bridge: resolve model hashes in same job
                    from app.models.phase4 import (
                        RepositorySnapshotModel,
                        LegacyModelRecord,
                        TargetBlueprintModel,
                        FeasibilityReportModel,
                    )
                    snap = await db.scalar(select(RepositorySnapshotModel).where(RepositorySnapshotModel.job_id == job_id, RepositorySnapshotModel.content_hash == ref_str).limit(1))
                    if snap:
                        ancestor = await db.scalar(select(Artifact).where(Artifact.job_id == job_id, Artifact.artifact_type == "RepositorySnapshot").order_by(Artifact.version.desc()).limit(1))
                    if not ancestor:
                        leg = await db.scalar(select(LegacyModelRecord).where(LegacyModelRecord.job_id == job_id, LegacyModelRecord.content_hash == ref_str).limit(1))
                        if leg:
                            ancestor = await db.scalar(select(Artifact).where(Artifact.job_id == job_id, Artifact.artifact_type == "LegacyModel").order_by(Artifact.version.desc()).limit(1))
                    if not ancestor:
                        bp = await db.scalar(select(TargetBlueprintModel).where(TargetBlueprintModel.job_id == job_id, TargetBlueprintModel.content_hash == ref_str).limit(1))
                        if bp:
                            ancestor = await db.scalar(select(Artifact).where(Artifact.job_id == job_id, Artifact.artifact_type.in_(["TargetBlueprint", "Blueprint"])).order_by(Artifact.version.desc()).limit(1))
                    if not ancestor:
                        feas = await db.scalar(select(FeasibilityReportModel).where(FeasibilityReportModel.job_id == job_id, FeasibilityReportModel.content_hash == ref_str).limit(1))
                        if feas:
                            ancestor = await db.scalar(select(Artifact).where(Artifact.job_id == job_id, Artifact.artifact_type == "FeasibilityReport").order_by(Artifact.version.desc()).limit(1))

                if not ancestor:
                    raise PlatformException(
                        code="INVALID_PROVENANCE",
                        message=f"Ancestor artifact reference '{ref_str}' does not exist.",
                        status_code=400,
                    )
                if ancestor.job_id != job_id:
                    raise PlatformException(
                        code="CROSS_JOB_LINEAGE_FORBIDDEN",
                        message=f"Cross-job lineage forbidden: ancestor '{ref_str}' belongs to job {ancestor.job_id}, not {job_id}.",
                        status_code=400,
                    )
                if ancestor.is_invalidated:
                    raise PlatformException(
                        code="INVALID_PROVENANCE",
                        message=f"Cannot derive artifact from invalidated ancestor '{ancestor.artifact_id}'.",
                        status_code=400,
                    )
                resolved_ancestor_artifacts.append(ancestor)

        # 5. Two-Stage Atomic Storage Protocol (DATA-07)
        # Stage A: Write to temporary staging key
        temp_id = uuid.uuid4().hex
        staging_key = f"staging/{job_id}/{temp_id}.tmp"
        content_hash, byte_size = await self.storage.put_object(
            key=staging_key,
            data=content_bytes,
            media_type=media_type,
        )

        # Stage B: Validate SHA-256 integrity
        actual_hash = self.storage.compute_sha256(content_bytes)
        if actual_hash != content_hash:
            await self.storage.delete_object(staging_key)
            raise PlatformException(
                code="ARTIFACT_CORRUPTION_DETECTED",
                message="Cryptographic SHA-256 calculation mismatch during staging write.",
                status_code=500,
            )

        # Stage C: Content-addressed final key
        suffix = ".zip" if media_type == "application/zip" else ".json"
        final_storage_key = f"jobs/{job_id}/artifacts/{canonical_type}_v{version}_{content_hash[:16]}{suffix}"
        if not await self.storage.object_exists(final_storage_key):
            await self.storage.put_object(
                key=final_storage_key,
                data=content_bytes,
                media_type=media_type,
            )

        # Stage D: Delete temporary staging key
        await self.storage.delete_object(staging_key)

        # 6. Create database record
        artifact_id = uuid.uuid4()
        artifact = Artifact(
            artifact_id=artifact_id,
            job_id=job_id,
            module_id=module_id,
            artifact_type=canonical_type,
            version=version,
            content_hash=content_hash,
            storage_path=final_storage_key,
            content_size_bytes=byte_size,
            media_type=media_type,
            producing_agent=producing_agent,
            derived_from=derived_from or [],
            extra_metadata=extra_metadata or {},
            schema_version=schema_version,
            producer_run_id=producer_run_id,
            is_invalidated=False,
        )
        db.add(artifact)

        # Insert foreign-key backed dependency records
        seen_ancestors: Set[uuid.UUID] = set()
        for anc in resolved_ancestor_artifacts:
            if anc.artifact_id not in seen_ancestors:
                seen_ancestors.add(anc.artifact_id)
                dep = ArtifactDependency(
                    dependency_id=uuid.uuid4(),
                    artifact_id=artifact_id,
                    ancestor_artifact_id=anc.artifact_id,
                    job_id=job_id,
                )
                db.add(dep)

        # 7. Record audit event
        actor_id = str(user.user_id) if user else producing_agent
        actor_type = "USER" if user else "AGENT"
        audit = AuditEvent(
            job_id=job_id,
            event_type="ARTIFACT_PUBLISHED",
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            target_resource=str(artifact_id),
            payload={
                "artifact_type": canonical_type,
                "version": version,
                "content_hash": content_hash,
                "size_bytes": byte_size,
                "schema_version": schema_version,
                "producer_run_id": str(producer_run_id) if producer_run_id else None,
            },
        )
        db.add(audit)

        # 8. Record Outbox event for workflow coordination
        outbox = WorkflowOutbox(
            job_id=job_id,
            idempotency_key=f"artifact_published:{artifact_id}",
            event_type="ARTIFACT_PUBLISHED",
            payload={
                "artifact_id": str(artifact_id),
                "artifact_type": canonical_type,
                "version": version,
                "content_hash": content_hash,
            },
            status="PENDING",
        )
        db.add(outbox)

        try:
            if commit:
                await db.commit()
            else:
                await db.flush()
            await db.refresh(artifact)
            return artifact
        except Exception as e:
            # Compensation (DATA-07): Only clean up staging key if it remained.
            # NEVER delete final_storage_key because concurrent workers publishing the same
            # content or an existing valid file must not be removed!
            await self.storage.delete_object(staging_key)
            await db.rollback()
            raise PlatformException(
                code="ARTIFACT_CREATION_FAILED",
                message=f"Failed to publish artifact metadata: {str(e)}",
                status_code=500,
            )

    async def create_artifact(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        artifact_type: str,
        version: int,
        content_bytes: bytes,
        producing_agent: str,
        derived_from: Optional[List[str]] = None,
        module_id: Optional[uuid.UUID] = None,
        media_type: str = "application/json",
        extra_metadata: Optional[Dict[str, Any]] = None,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
        producer_run_id: Optional[uuid.UUID] = None,
        schema_version: str = "1.0.0",
        commit: bool = True,
    ) -> Artifact:
        """Backward-compatible wrapper delegating to publish_artifact."""
        return await self.publish_artifact(
            db=db,
            job_id=job_id,
            artifact_type=artifact_type,
            version=version,
            content_bytes=content_bytes,
            producing_agent=producing_agent,
            derived_from=derived_from,
            module_id=module_id,
            media_type=media_type,
            extra_metadata=extra_metadata,
            user=user,
            correlation_id=correlation_id,
            producer_run_id=producer_run_id,
            schema_version=schema_version,
            commit=commit,
        )

    async def invalidate_artifact_and_downstream(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        artifact_id: uuid.UUID,
        reason: str,
        user: Optional[User] = None,
        correlation_id: Optional[str] = None,
        commit: bool = True,
    ) -> List[uuid.UUID]:
        """Traverses the dependency graph and revokes the artifact, all downstream deliverables, and gates."""
        target_art = await self.get_artifact(db, job_id, artifact_id)

        # BFS traversal over artifact_dependencies
        invalidated_ids: List[uuid.UUID] = []
        queue: List[uuid.UUID] = [artifact_id]
        visited: Set[uuid.UUID] = {artifact_id}

        while queue:
            curr = queue.pop(0)
            dep_stmt = select(ArtifactDependency.artifact_id).where(
                ArtifactDependency.ancestor_artifact_id == curr,
                ArtifactDependency.job_id == job_id,
            )
            dep_res = await db.execute(dep_stmt)
            children = dep_res.scalars().all()
            for child_id in children:
                if child_id not in visited:
                    visited.add(child_id)
                    queue.append(child_id)

        now = utc_now()
        for art_id in visited:
            art_stmt = select(Artifact).where(Artifact.artifact_id == art_id, Artifact.job_id == job_id)
            art_res = await db.execute(art_stmt)
            art = art_res.scalar_one_or_none()
            if art and not art.is_invalidated:
                art.is_invalidated = True
                art.invalidated_at = now
                art.invalidation_reason = (
                    reason if art_id == artifact_id else f"Cascaded invalidation from ancestor {artifact_id}: {reason}"
                )
                invalidated_ids.append(art_id)

                actor_id = str(user.user_id) if user else "SYSTEM"
                actor_type = "USER" if user else "SYSTEM"
                db.add(
                    AuditEvent(
                        job_id=job_id,
                        event_type="ARTIFACT_INVALIDATED",
                        actor_type=actor_type,
                        actor_id=actor_id,
                        correlation_id=correlation_id,
                        target_resource=str(art_id),
                        payload={"reason": art.invalidation_reason},
                    )
                )

        # Invalidate any WorkflowGate referencing the invalidated artifacts
        invalidated_id_strs = {str(i) for i in visited}
        gate_stmt = select(WorkflowGate).where(WorkflowGate.job_id == job_id)
        gate_res = await db.execute(gate_stmt)
        gates = gate_res.scalars().all()

        for gate in gates:
            gate_art_set = set(gate.artifact_ids or [])
            if gate_art_set.intersection(invalidated_id_strs) and gate.status in ("PENDING", "APPROVED"):
                gate.status = "INVALIDATED"
                gate.blocking_reason = (
                    f"Gate invalidated due to revocation of artifact {artifact_id}: {reason}"
                )
                db.add(
                    AuditEvent(
                        job_id=job_id,
                        event_type="GATE_INVALIDATED",
                        actor_type="SYSTEM",
                        actor_id="SUPERVISOR",
                        correlation_id=correlation_id,
                        target_resource=str(gate.gate_id),
                        payload={"gate_type": gate.gate_type, "reason": gate.blocking_reason},
                    )
                )
                db.add(
                    WorkflowOutbox(
                        job_id=job_id,
                        idempotency_key=f"gate_invalidated:{gate.gate_id}:{uuid.uuid4().hex[:8]}",
                        event_type="GATE_INVALIDATED",
                        payload={"gate_id": str(gate.gate_id), "gate_type": gate.gate_type},
                        status="PENDING",
                    )
                )

        # Record outbox event for artifact invalidation
        db.add(
            WorkflowOutbox(
                job_id=job_id,
                idempotency_key=f"artifact_invalidated:{artifact_id}:{uuid.uuid4().hex[:8]}",
                event_type="ARTIFACT_INVALIDATED",
                payload={
                    "root_artifact_id": str(artifact_id),
                    "invalidated_count": len(invalidated_ids),
                    "invalidated_ids": [str(i) for i in invalidated_ids],
                    "reason": reason,
                },
                status="PENDING",
            )
        )

        if commit:
            await db.commit()
        else:
            await db.flush()

        return invalidated_ids

    async def list_artifacts(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        artifact_type: Optional[str] = None,
        include_invalidated: bool = True,
    ) -> List[Artifact]:
        query = select(Artifact).where(Artifact.job_id == job_id)
        if artifact_type:
            canonical_type = normalize_artifact_type(artifact_type)
            query = query.where(Artifact.artifact_type.in_([canonical_type, artifact_type]))
        if not include_invalidated:
            query = query.where(Artifact.is_invalidated.is_(False))
        query = query.order_by(Artifact.version.asc())
        res = await db.execute(query)
        return list(res.scalars().all())

    async def get_artifact(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        artifact_id: uuid.UUID,
    ) -> Artifact:
        stmt = select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.artifact_id == artifact_id,
        )
        res = await db.execute(stmt)
        artifact = res.scalar_one_or_none()
        if not artifact:
            raise NotFoundException(resource="Artifact", resource_id=str(artifact_id))
        return artifact

    async def get_artifact_content(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        artifact_id: uuid.UUID,
    ) -> Tuple[Artifact, bytes]:
        """Retrieves raw artifact bytes and verifies SHA-256 cryptographic integrity."""
        artifact = await self.get_artifact(db, job_id, artifact_id)
        content_bytes = await self.storage.get_object(artifact.storage_path)

        # Integrity check: verify content hash against recorded cryptographic checksum
        actual_hash = self.storage.compute_sha256(content_bytes)
        if actual_hash != artifact.content_hash:
            raise PlatformException(
                code="ARTIFACT_CORRUPTION_DETECTED",
                message=f"Cryptographic SHA-256 mismatch for artifact '{artifact.artifact_type}' v{artifact.version}.",
                status_code=500,
            )

        return artifact, content_bytes


artifact_service = ArtifactService()
