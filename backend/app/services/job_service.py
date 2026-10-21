"""Transactional Modernization Job Service with audit integrity and state machine validation."""

from decimal import Decimal
from typing import List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
        # Validate repository URL syntax and provider allowlist
        self.git_adapter.validate_source_url(payload.source_repository)

        # Validate pinned commit format if provided
        pinned_commit = None
        if payload.pinned_commit and payload.pinned_commit.strip():
            clean_commit = payload.pinned_commit.strip()
            if not re.match(r"^[0-9a-fA-F]{7,40}$", clean_commit):
                raise ValidationException(
                    message="Invalid pinned commit SHA format.",
                    details=[ErrorDetail(field="pinned_commit", issue="Must be a valid 7 to 40 character hexadecimal Git SHA.")]
                )
            pinned_commit = clean_commit

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
            target_stack=payload.target_stack or "TypeScript / NestJS",
            status=JobStatus.CREATED.value,
            budget_limit_usd=Decimal(str(payload.budget)),
            budget_used_usd=Decimal("0.00"),
            max_repair_attempts=payload.max_repair_attempts,
            owner_user_id=user.user_id,
            description=payload.constraints,
            stack_metadata=structured_metadata if structured_metadata is not None else payload.stack_metadata,
        )
        db.add(new_job)

        # Grant owner membership with ADMIN role
        membership = JobMembership(
            job_id=job_id,
            user_id=user.user_id,
            role_id="ADMIN",
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
        if user.role == "SUPER_ADMIN":
            query = select(Job)
            count_query = select(func.count(Job.job_id))
            if status:
                query = query.where(Job.status == status)
                count_query = count_query.where(Job.status == status)
        else:
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
        """Validates state machine and cancels active job transactionally."""
        current_status = JobStatus(job.status)
        if current_status == JobStatus.CANCELLED:
            return job  # Idempotent cancellation

        # Enforce DAG state machine constraints
        JobStateMachine.validate_transition(current_status, JobStatus.CANCELLED)

        job.status = JobStatus.CANCELLED.value

        audit = AuditEvent(
            job_id=job.job_id,
            event_type="JOB_CANCELLED",
            actor_type="USER",
            actor_id=str(user.user_id),
            correlation_id=correlation_id,
            target_resource=str(job.job_id),
            payload={"previous_status": current_status.value},
        )
        db.add(audit)
        await db.commit()
        await db.refresh(job)
        return job
