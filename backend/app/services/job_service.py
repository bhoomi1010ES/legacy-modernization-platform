"""Transactional Modernization Job Service with audit integrity and state machine validation."""

from decimal import Decimal
from typing import List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

import re
from app.core.errors import ConflictException, NotFoundException, ValidationException, ErrorDetail
from app.domain.state_machine import JobStateMachine
from app.models.audit import AuditEvent
from app.models.job import Job, JobMembership
from app.models.user import User
from app.schemas.jobs import JobCreateRequest, JobStatus
from app.services.git_adapter import ControlledGitAdapter


class JobService:
    """Orchestrates job lifecycle, membership provisioning, and state progression."""

    def __init__(self, git_adapter: Optional[ControlledGitAdapter] = None):
        self.git_adapter = git_adapter or ControlledGitAdapter()

    async def create_job(
        self,
        db: AsyncSession,
        payload: JobCreateRequest,
        user: User,
        correlation_id: Optional[str] = None,
    ) -> Job:
        """Transactionally creates a Job, Owner JobMembership, and initial AuditEvent."""
        is_local_source = (
            (payload.source_type == "local")
            or (payload.source_repository and payload.source_repository.startswith("local://"))
            or (payload.source_repository and Path(payload.source_repository).is_absolute())
        )

        if is_local_source:
            if not payload.source_repository or len(payload.source_repository.strip()) < 3:
                raise ValidationException("Local source directory path cannot be empty.")
            # If preview_snapshot_id is provided, verify it exists and is active
            if payload.preview_snapshot_id:
                from app.services.local_source_adapter import LocalSourceAdapter
                adapter = LocalSourceAdapter()
                adapter.get_staged_snapshot(payload.preview_snapshot_id)
        else:
            self.git_adapter.validate_source_url(payload.source_repository)

            # If a private repository token was supplied, validate host restriction
            if payload.git_token and payload.git_token.strip():
                from urllib.parse import urlparse
                parsed_host = (urlparse(payload.source_repository).hostname or "").lower()
                if parsed_host != "github.com":
                    from app.services.git_adapter import GitSecurityException
                    raise GitSecurityException(
                        f"GitHub Personal Access Token cannot be used with host '{parsed_host}'. Credentials are restricted strictly to github.com.",
                        issue="git_token is restricted strictly to github.com repositories."
                    )

            # Validate pinned commit format if provided
            if payload.pinned_commit and payload.pinned_commit.strip():
                clean_commit = payload.pinned_commit.strip()
                if not re.match(r"^[0-9a-fA-F]{7,40}$", clean_commit):
                    raise ValidationException(
                        message="Invalid pinned commit SHA format.",
                        details=[ErrorDetail(field="pinned_commit", issue="Must be a valid 7 to 40 character hexadecimal Git SHA.")]
                    )
                pinned_commit = clean_commit

        pinned_commit = payload.pinned_commit.strip() if payload.pinned_commit and not is_local_source else None

        # Normalize and structure stack_metadata separating automated detection from user overrides
        structured_metadata = None
        if payload.stack_metadata or payload.user_overrides or pinned_commit:
            raw_meta = payload.stack_metadata or {}
            overrides = payload.user_overrides or {}
            
            # If already wrapped, preserve inner detected
            detected_part = raw_meta.get("detected") if isinstance(raw_meta, dict) and "detected" in raw_meta else raw_meta

            # Compute effective profile
            effective_profile = dict(detected_part) if isinstance(detected_part, dict) else {}
            if overrides:
                for k, v in overrides.items():
                    effective_profile[k] = v

            structured_metadata = {
                "detected": detected_part,
                "overrides": overrides,
                "effective": effective_profile,
                "pinned_commit": pinned_commit or (detected_part.get("resolved_commit") if isinstance(detected_part, dict) else None),
                "requested_revision": payload.source_revision or "main",
            }

        job_id = uuid.uuid4()
        new_job = Job(
            job_id=job_id,
            name=payload.name,
            source_repository=payload.source_repository,
            source_revision=payload.source_revision or "main",
            source_stack=payload.source_stack or "Java 8 / Spring Boot",
            target_stack=(payload.target_stack or "TypeScript / NestJS")[:100],
            status=JobStatus.CREATED.value,
            budget_limit_usd=Decimal(str(payload.budget)),
            budget_used_usd=Decimal("0.00"),
            max_repair_attempts=payload.max_repair_attempts,
            owner_user_id=user.user_id,
            description=payload.constraints,
            stack_metadata=structured_metadata if structured_metadata is not None else payload.stack_metadata,
        )
        db.add(new_job)

        # Grant owner membership with least-privilege DEVELOPER role (SEC-03)
        membership = JobMembership(
            job_id=job_id,
            user_id=user.user_id,
                    )
        db.add(membership)

        # Append initial transactional audit record
        audit = AuditEvent(
            job_id=job_id,
            event_type="JOB_CREATED",
            actor_type="USER",
            actor_id=str(user.user_id),
            correlation_id=correlation_id,
            target_resource=str(job_id),
            payload={
                "name": new_job.name,
                "source_repository": new_job.source_repository,
                "budget_limit_usd": float(new_job.budget_limit_usd),
                "owner_email": user.email,
                "pinned_commit": pinned_commit,
                "has_overrides": bool(payload.user_overrides),
            },
        )
        db.add(audit)

        # Commit atomically
        await db.commit()
        await db.refresh(new_job)
        return new_job

    async def list_jobs(
        self,
        db: AsyncSession,
        user: User,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> Tuple[List[Job], int]:
        """Lists authorized jobs with deterministic ordering and pagination."""
        query = (
            select(Job)
            .join(JobMembership, JobMembership.job_id == Job.job_id)
            .where(JobMembership.user_id == user.user_id)
        )
        count_query = (
            select(func.count(Job.job_id))
            .join(JobMembership, JobMembership.job_id == Job.job_id)
            .where(JobMembership.user_id == user.user_id)
        )
        if status:
            query = query.where(Job.status == status)
            count_query = count_query.where(Job.status == status)

        query = query.order_by(Job.created_at.desc()).offset(offset).limit(limit)

        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        items_res = await db.execute(query)
        jobs = list(items_res.scalars().all())

        return jobs, total

    async def get_job_by_id(self, db: AsyncSession, job_id: uuid.UUID) -> Optional[Job]:
        stmt = select(Job).where(Job.job_id == job_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    async def cancel_job(
        self,
        db: AsyncSession,
        job: Job,
        user: User,
        correlation_id: Optional[str] = None,
    ) -> Job:
        """Compatibility facade; cancellation is owned by SupervisorService."""
        from app.services.supervisor_service import supervisor_service
        return await supervisor_service.cancel(
            db, job.job_id, actor_id=str(user.user_id),
            correlation_id=correlation_id,
        )

    async def acquire_intake_workspace(
        self,
        db: AsyncSession,
        job_id: str,
        repo_url: str,
        revision: str = "main",
        pinned_commit: Optional[str] = None,
        git_token: Optional[str] = None,
        source_type: str = "git",
        preview_snapshot_id: Optional[str] = None,
        snapshot_fingerprint: Optional[str] = None,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> Tuple[Path, str]:
        """Compatibility facade for the authoritative workspace service.

        IntakeAgent is the normal caller. Keeping this facade prevents older
        command handlers from reintroducing an independent clone/path policy.
        """
        from app.services.repository_workspace_service import repository_workspace_service

        return await repository_workspace_service.stage_repository(
            db,
            job_id,
            source=repo_url,
            revision=revision,
            pinned_commit=pinned_commit,
            git_token=git_token,
            preview_snapshot_id=preview_snapshot_id,
            snapshot_fingerprint=snapshot_fingerprint,
        )

