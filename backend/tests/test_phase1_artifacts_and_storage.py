"""Phase 1 Artifact Versioning, SHA-256 Integrity, Lineage, and Storage Tests."""

import hashlib
import json
import pytest
import uuid
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.errors import ConflictException, NotFoundException, PlatformException
from app.core.storage import InMemoryStorageAdapter, LocalStorageAdapter, StorageException, StorageNotFoundException
from app.models.artifact import Artifact
from app.models.job import Job
from app.models.user import User
from app.services.artifact_service import ArtifactService


@pytest.mark.asyncio
async def test_storage_adapter_round_trip_and_sha256():
    """Proves storage adapter computes accurate SHA-256 checksums and retrieves content."""
    adapter = InMemoryStorageAdapter()
    data = b'{"module": "Authentication", "tests": 42}'
    expected_hash = hashlib.sha256(data).hexdigest()

    # Store
    content_hash, size = await adapter.put_object("jobs/job-1/test.json", data)
    assert content_hash == expected_hash
    assert size == len(data)

    # Check exists
    assert await adapter.object_exists("jobs/job-1/test.json") is True
    assert await adapter.object_exists("jobs/job-1/missing.json") is False

    # Retrieve
    retrieved = await adapter.get_object("jobs/job-1/test.json")
    assert retrieved == data

    # Delete
    assert await adapter.delete_object("jobs/job-1/test.json") is True
    assert await adapter.object_exists("jobs/job-1/test.json") is False


@pytest.mark.asyncio
async def test_storage_adapter_missing_object_raises_not_found():
    """Proves accessing non-existent key raises StorageNotFoundException."""
    adapter = InMemoryStorageAdapter()
    with pytest.raises(StorageNotFoundException):
        await adapter.get_object("nonexistent-key.json")


def test_local_storage_path_traversal_rejection(tmp_path):
    """Proves storage adapter rejects path traversal attempts in keys."""
    adapter = LocalStorageAdapter(base_path=str(tmp_path))
    with pytest.raises(StorageException):
        import asyncio
        asyncio.run(adapter.put_object("../../secret.txt", b"evil"))


@pytest.mark.asyncio
async def test_artifact_duplicate_version_rejected():
    """Proves publishing an existing version of an artifact is strictly prohibited (immutability)."""
    storage = InMemoryStorageAdapter()
    service = ArtifactService(storage_adapter=storage)

    async with AsyncSessionLocal() as db_session:
        # Use existing test job
        job_id = uuid.uuid4()
        user_res = await db_session.execute(select(User).limit(1))
        owner = user_res.scalar_one()

        job = Job(
            job_id=job_id,
            name="Artifact Immutability Job",
            source_repository="https://github.com/acme/immutability",
            status="ANALYZING",
            owner_user_id=owner.user_id,
        )
        db_session.add(job)
        await db_session.commit()

        content1 = b'{"version": 1, "data": "first"}'
        art1 = await service.create_artifact(
            db=db_session,
            job_id=job_id,
            artifact_type="RepoInventory",
            version=1,
            content_bytes=content1,
            producing_agent="IntakeAgent",
        )
        assert art1.version == 1

        # Attempt publishing duplicate version 1 -> Must raise ConflictException
        content2 = b'{"version": 1, "data": "overwrite_attempt"}'
        with pytest.raises(ConflictException):
            await service.create_artifact(
                db=db_session,
                job_id=job_id,
                artifact_type="RepoInventory",
                version=1,
                content_bytes=content2,
                producing_agent="IntakeAgent",
            )


@pytest.mark.asyncio
async def test_artifact_lineage_and_integrity_check():
    """Proves artifact content verification checks SHA-256 and lineage tracking."""
    storage = InMemoryStorageAdapter()
    service = ArtifactService(storage_adapter=storage)

    async with AsyncSessionLocal() as db_session:
        job_id = uuid.uuid4()
        user_res = await db_session.execute(select(User).limit(1))
        owner = user_res.scalar_one()

        job = Job(
            job_id=job_id,
            name="Lineage Test Job",
            source_repository="https://github.com/acme/lineage",
            status="PLANNING",
            owner_user_id=owner.user_id,
        )
        db_session.add(job)
        await db_session.commit()

        # Step 1: Create Parent Artifact v1
        v1_bytes = b'{"spec": "parent"}'
        art_v1 = await service.create_artifact(
            db=db_session,
            job_id=job_id,
            artifact_type="TargetBlueprint",
            version=1,
            content_bytes=v1_bytes,
            producing_agent="ArchitectAgent",
        )

        # Step 2: Create Child Artifact v2 derived from v1 hash
        v2_bytes = b'{"spec": "child_extended"}'
        art_v2 = await service.create_artifact(
            db=db_session,
            job_id=job_id,
            artifact_type="TargetBlueprint",
            version=2,
            content_bytes=v2_bytes,
            producing_agent="ArchitectAgent",
            derived_from=[art_v1.content_hash],
        )

        assert art_v2.version == 2
        assert art_v1.content_hash in art_v2.derived_from

        # Step 3: Retrieve content and verify SHA-256 matches
        retrieved_art, bytes_out = await service.get_artifact_content(
            db=db_session,
            job_id=job_id,
            artifact_id=art_v2.artifact_id,
        )
        assert bytes_out == v2_bytes
        assert storage.compute_sha256(bytes_out) == retrieved_art.content_hash
