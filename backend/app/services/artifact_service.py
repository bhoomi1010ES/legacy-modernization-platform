"""Artifact versioning, cryptographic integrity validation, and lineage service."""

import json
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, NotFoundException, PlatformException
from app.core.storage import StorageAdapter, get_storage_adapter
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.user import User


class ArtifactService:
    """Manages immutable deliverable publishing, staged writes, and lineage tracking."""

    def __init__(self, storage_adapter: Optional[StorageAdapter] = None):
        self.storage = storage_adapter or get_storage_adapter()

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
        commit: bool = True,
    ) -> Artifact:
        """Publishes an immutable artifact version using staged-write compensation."""
        # 1. Enforce uniqueness: an existing version must never be overwritten
        stmt = select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == artifact_type,
            Artifact.version == version,
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ConflictException(
                f"Artifact '{artifact_type}' version {version} already exists for this job. Artifacts are strictly immutable."
            )

        storage_key = f"jobs/{job_id}/artifacts/{artifact_type}_v{version}.json"

        # 2. Staged write to storage abstraction
        content_hash, byte_size = await self.storage.put_object(
            key=storage_key,
            data=content_bytes,
            media_type=media_type,
        )

        # 3. Create database record
        artifact_id = uuid.uuid4()
        artifact = Artifact(
            artifact_id=artifact_id,
            job_id=job_id,
            module_id=module_id,
            artifact_type=artifact_type,
            version=version,
            content_hash=content_hash,
            storage_path=storage_key,
            content_size_bytes=byte_size,
            media_type=media_type,
            producing_agent=producing_agent,
            derived_from=derived_from or [],
            extra_metadata=extra_metadata or {},
        )
        db.add(artifact)

        # 4. Record audit event
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
                "artifact_type": artifact_type,
                "version": version,
                "content_hash": content_hash,
                "size_bytes": byte_size,
            },
        )
        db.add(audit)

        try:
            if commit:
                await db.commit()
            else:
                await db.flush()
            await db.refresh(artifact)
            return artifact
        except Exception as e:
            # Compensation: delete staged object from storage if database transaction fails
            await self.storage.delete_object(storage_key)
            await db.rollback()
            raise PlatformException(
                code="ARTIFACT_CREATION_FAILED",
                message=f"Failed to publish artifact metadata: {str(e)}",
                status_code=500,
            )

    async def list_artifacts(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        artifact_type: Optional[str] = None,
    ) -> List[Artifact]:
        query = select(Artifact).where(Artifact.job_id == job_id)
        if artifact_type:
            query = query.where(Artifact.artifact_type == artifact_type)
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
