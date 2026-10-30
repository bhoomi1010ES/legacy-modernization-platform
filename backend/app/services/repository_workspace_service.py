"""Authoritative, job-scoped repository workspace lifecycle.

The durable Job row is the cross-process coordination boundary. Filesystem
changes are prepared beside the canonical workspace and atomically promoted
only after Git and repository identity validation succeeds.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Optional
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ROOT_DIR
from app.core.errors import (
    ConflictException,
    NotFoundException,
    WorkspaceCorruptedException,
    WorkspaceGitInvalidException,
    WorkspaceInvalidException,
    WorkspaceNotFoundException,
    WorkspaceRecoveryFailedException,
    WorkspaceWrongRepositoryException,
)
from app.models.audit import AuditEvent
from app.models.base import utc_now
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.phase4 import RepositorySnapshotModel
from app.services.git_adapter import ControlledGitAdapter

logger = logging.getLogger(__name__)

WORKSPACE_SIDECAR = ".rebase_workspace.json"
ACTIVE_MODULE_STATUSES = {"LEASED", "QUEUED", "RUNNING", "GENERATED", "VERIFYING"}
ACTIVE_ATTEMPT_STATUSES = {"QUEUED", "RUNNING", "GENERATED", "VERIFYING"}
NON_CLEANABLE_JOB_STATUSES = {
    "CREATED", "INTAKE", "ANALYZING", "AWAITING_GATE_G1", "CHARACTERIZING",
    "AWAITING_GATE_G2", "PLANNING", "AWAITING_GATE_G3", "CONVERTING",
    "VERIFYING", "INTEGRATING", "AWAITING_GATE_G4", "PAUSED",
}


class WorkspaceValidationResult(BaseModel):
    """Structured readiness result used by dispatch, recovery, and the UI."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_ready: bool
    path: Optional[Path] = None
    commit_sha: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class RepositoryWorkspaceService:
    """Single repository path, validation, staging, recovery and cleanup authority."""

    def __init__(
        self,
        workspace_base: Optional[Path] = None,
        workspace_root: Optional[Path] = None,
        allow_local_repos_for_test: bool = True,
        max_recovery_attempts: int = 2,
    ) -> None:
        configured = os.getenv("GIT_WORKSPACE_BASE")
        target = workspace_root or workspace_base or (
            Path(configured) if configured else ROOT_DIR / "repo_workspaces"
        )
        self.workspace_base = Path(target).resolve()
        self.workspace_base.mkdir(parents=True, exist_ok=True)
        self.workspace_root = self.workspace_base
        self.max_recovery_attempts = max(1, max_recovery_attempts)
        self.git_adapter = ControlledGitAdapter(
            workspace_base=str(self.workspace_base),
            allow_local_repos_for_test=allow_local_repos_for_test,
        )

    @staticmethod
    def _clean_job_id(job_id: str | UUID) -> str:
        value = str(job_id)
        if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise WorkspaceInvalidException("Job ID cannot be mapped to a safe workspace path.")
        return value

    @staticmethod
    def _source_identity(source: Optional[str]) -> str:
        """Canonicalize source identity while stripping URL credentials."""
        value = (source or "").strip()
        if not value:
            return ""
        if value.startswith("local://"):
            value = value.removeprefix("local://")
        candidate = Path(value)
        if candidate.is_absolute():
            resolved = str(candidate.resolve())
            return resolved.casefold() if os.name == "nt" else resolved
        parsed = urlsplit(value)
        if parsed.scheme and parsed.netloc:
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            path = parsed.path.rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            return urlunsplit((parsed.scheme.lower(), host.lower(), path, "", ""))
        return value.rstrip("/")

    def get_workspace_path(self, job_id: str | UUID) -> Path:
        """Return the only canonical workspace path for a job."""
        clean_id = self._clean_job_id(job_id)
        path = (self.workspace_base / f"job_{clean_id}").resolve()
        try:
            path.relative_to(self.workspace_base)
        except ValueError as exc:
            raise WorkspaceInvalidException("Resolved workspace escapes its configured root.") from exc
        return path

    def _safe_git_exec(
        self,
        cwd: Path,
        args: list[str],
        *,
        timeout: int = 30,
        deterministic_commit: bool = False,
    ) -> tuple[int, str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if key.upper()
            in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
        }
        env.update(
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
        )
        if deterministic_commit:
            env.update(
                GIT_AUTHOR_NAME="Rebase Workspace",
                GIT_AUTHOR_EMAIL="workspace@rebase.invalid",
                GIT_COMMITTER_NAME="Rebase Workspace",
                GIT_COMMITTER_EMAIL="workspace@rebase.invalid",
                GIT_AUTHOR_DATE="2000-01-01T00:00:00+00:00",
                GIT_COMMITTER_DATE="2000-01-01T00:00:00+00:00",
            )
        command = [
            "git", "-c", "safe.directory=*", "-c", f"core.hooksPath={os.devnull}",
            "-c", "protocol.ext.allow=never", "-c", "core.longpaths=true",
            "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false",
            "-c", "submodule.recurse=false", "-C", str(cwd), *args,
        ]
        try:
            result = subprocess.run(
                command, cwd=str(cwd), capture_output=True, text=True,
                timeout=timeout, env=env, shell=False,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except Exception as exc:
            return 1, "", str(exc)

    @staticmethod
    def _raise_validation(code: str, message: str) -> None:
        error_types = {
            "WORKSPACE_NOT_FOUND": WorkspaceNotFoundException,
            "WORKSPACE_INVALID": WorkspaceInvalidException,
            "WORKSPACE_CORRUPTED": WorkspaceCorruptedException,
            "WORKSPACE_WRONG_REPOSITORY": WorkspaceWrongRepositoryException,
            "WORKSPACE_GIT_INVALID": WorkspaceGitInvalidException,
        }
        raise error_types.get(code, WorkspaceInvalidException)(message)

    async def validate_workspace(
        self,
        job_id: str | UUID,
        expected_commit: Optional[str] = None,
        expected_source: Optional[str] = None,
        *,
        workspace_path: Optional[Path] = None,
        raise_on_error: bool = False,
        raise_for_failure: Optional[bool] = None,
    ) -> WorkspaceValidationResult:
        """Validate path, Git health, clean state, pinned commit and job identity."""
        if raise_for_failure is not None:
            raise_on_error = raise_for_failure
        clean_id = self._clean_job_id(job_id)
        canonical_path = self.get_workspace_path(clean_id)
        path = (workspace_path or canonical_path).resolve()
        logger.info("workspace.validation.started | job_id=%s workspace_path=%s", clean_id, path)

        def fail(code: str, message: str) -> WorkspaceValidationResult:
            logger.warning(
                "workspace.validation.failed | job_id=%s workspace_path=%s code=%s reason=%s",
                clean_id, path, code, message,
            )
            if raise_on_error:
                self._raise_validation(code, message)
            return WorkspaceValidationResult(
                is_ready=False, path=path, error_code=code, error_message=message,
            )

        try:
            path.relative_to(self.workspace_base)
        except ValueError:
            return fail("WORKSPACE_INVALID", "Workspace is outside the configured repository root.")
        if workspace_path is None and path != canonical_path:
            return fail("WORKSPACE_INVALID", "Workspace does not use the canonical job-scoped path.")
        if not path.exists():
            return fail("WORKSPACE_NOT_FOUND", f"Workspace directory '{path}' does not exist.")
        if not path.is_dir():
            return fail("WORKSPACE_INVALID", f"Workspace path '{path}' is not a directory.")
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            return fail("WORKSPACE_INVALID", "Workspace root cannot be a symlink or junction.")
        try:
            if not any(path.iterdir()):
                return fail("WORKSPACE_CORRUPTED", "Workspace directory is empty.")
        except OSError as exc:
            return fail("WORKSPACE_INVALID", f"Workspace directory is inaccessible: {exc}")

        git_marker = path / ".git"
        if not git_marker.exists() or git_marker.is_symlink():
            return fail("WORKSPACE_GIT_INVALID", "Workspace has no supported .git metadata.")
        code, inside, error = self._safe_git_exec(path, ["rev-parse", "--is-inside-work-tree"])
        if code or inside.lower() != "true":
            return fail("WORKSPACE_GIT_INVALID", f"Git cannot open the workspace: {error or inside}")
        code, head, error = self._safe_git_exec(path, ["rev-parse", "--verify", "HEAD^{commit}"])
        if code or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head):
            return fail("WORKSPACE_GIT_INVALID", f"Workspace has no valid HEAD commit: {error}")
        code, tracked, error = self._safe_git_exec(path, ["ls-files", "-z"])
        if code:
            return fail("WORKSPACE_GIT_INVALID", f"Git cannot enumerate source files: {error}")
        if not [item for item in tracked.split("\x00") if item]:
            return fail("WORKSPACE_CORRUPTED", "Workspace contains no tracked source files.")
        code, status, error = self._safe_git_exec(
            path, ["status", "--porcelain=v1", "--untracked-files=all"]
        )
        if code:
            return fail("WORKSPACE_GIT_INVALID", f"Git status failed: {error}")
        dirty = [line for line in status.splitlines() if line != f"?? {WORKSPACE_SIDECAR}"]
        if dirty:
            return fail(
                "WORKSPACE_CORRUPTED",
                "Authoritative workspace has unexpected tracked or untracked changes.",
            )

        sidecar = path / WORKSPACE_SIDECAR
        if not sidecar.is_file() or sidecar.is_symlink():
            return fail("WORKSPACE_WRONG_REPOSITORY", "Workspace identity metadata is missing.")
        try:
            identity = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            return fail("WORKSPACE_CORRUPTED", f"Workspace identity metadata is invalid: {exc}")
        if identity.get("schema_version") != 1 or identity.get("job_id") != clean_id:
            return fail(
                "WORKSPACE_WRONG_REPOSITORY",
                "Workspace identity does not belong to the requested job.",
            )
        staged_source = self._source_identity(identity.get("source_repository"))
        wanted_source = self._source_identity(expected_source)
        if wanted_source and staged_source != wanted_source:
            return fail(
                "WORKSPACE_WRONG_REPOSITORY",
                "Workspace source identity does not match the job repository.",
            )
        sidecar_commit = str(identity.get("commit_sha") or "").lower()
        if sidecar_commit != head.lower():
            return fail(
                "WORKSPACE_CORRUPTED",
                "Workspace HEAD no longer matches its staged snapshot identity.",
            )
        if expected_commit and expected_commit not in {"HEAD", "LOCAL"}:
            wanted = expected_commit.strip().lower()
            if not (head.lower().startswith(wanted) or wanted.startswith(head.lower())):
                return fail(
                    "WORKSPACE_WRONG_REPOSITORY",
                    "Workspace HEAD does not match the authoritative repository snapshot.",
                )

        logger.info(
            "workspace.validation.completed | job_id=%s workspace_path=%s commit=%s ready=true",
            clean_id, path, head,
        )
        return WorkspaceValidationResult(is_ready=True, path=path, commit_sha=head)

    async def is_workspace_ready(
        self,
        job_id: str | UUID,
        expected_commit: Optional[str] = None,
        expected_source: Optional[str] = None,
    ) -> bool:
        result = await self.validate_workspace(
            job_id, expected_commit=expected_commit, expected_source=expected_source,
        )
        return result.is_ready

    async def _locked_job(self, db: AsyncSession, job: Job | UUID | str) -> Job:
        job_id = job.job_id if isinstance(job, Job) else UUID(str(job))
        locked = await db.scalar(
            select(Job).where(Job.job_id == job_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked is None:
            raise NotFoundException("Job", str(job_id))
        return locked

    async def _expected_commit(self, db: AsyncSession, job: Job) -> Optional[str]:
        snapshot = await db.scalar(
            select(RepositorySnapshotModel)
            .where(RepositorySnapshotModel.job_id == job.job_id)
            .order_by(RepositorySnapshotModel.version.desc()).limit(1)
        )
        if snapshot and snapshot.commit_sha:
            return snapshot.commit_sha
        metadata = job.stack_metadata if isinstance(job.stack_metadata, dict) else {}
        return metadata.get("pinned_commit")

    def _audit(
        self,
        db: AsyncSession,
        job: Job,
        event_type: str,
        correlation_id: Optional[str],
        payload: dict,
    ) -> None:
        db.add(AuditEvent(
            job_id=job.job_id, event_type=event_type, actor_type="SYSTEM",
            actor_id="repository_workspace_service", correlation_id=correlation_id,
            target_resource=str(job.job_id), payload=payload,
        ))

    def _write_sidecar(
        self,
        workspace_path: Path,
        *,
        job_id: str,
        source_url: str,
        commit_sha: str,
        source_type: str,
        source_revision: Optional[str] = None,
    ) -> None:
        """Write non-secret job/source/commit identity beside the Git metadata."""
        data = {
            "schema_version": 1,
            "job_id": self._clean_job_id(job_id),
            "source_type": source_type,
            "source_repository": self._source_identity(source_url),
            "source_revision": source_revision,
            "commit_sha": commit_sha.lower(),
            "staged_at": utc_now().isoformat(),
        }
        (workspace_path / WORKSPACE_SIDECAR).write_text(
            json.dumps(data, sort_keys=True, indent=2), encoding="utf-8"
        )

    def _initialize_materialized_git(self, path: Path) -> str:
        for command in (["init"], ["add", "-A"]):
            code, _, error = self._safe_git_exec(path, command)
            if code:
                raise WorkspaceGitInvalidException(
                    f"Unable to initialize materialized repository Git state: {error}"
                )
        code, _, error = self._safe_git_exec(
            path,
            ["commit", "--allow-empty", "-m", "Deterministic repository intake snapshot"],
            deterministic_commit=True,
        )
        if code:
            raise WorkspaceGitInvalidException(
                f"Unable to commit materialized repository snapshot: {error}"
            )
        code, commit, error = self._safe_git_exec(path, ["rev-parse", "HEAD"])
        if code:
            raise WorkspaceGitInvalidException(f"Unable to resolve materialized snapshot: {error}")
        return commit

    def _materialize_source(
        self,
        job: Job,
        destination: Path,
        *,
        git_token: Optional[str],
        preview_snapshot_id: Optional[str],
        snapshot_fingerprint: Optional[str],
        workspace_override: Optional[Path],
        pinned_commit: Optional[str],
    ) -> tuple[str, str]:
        source = job.source_repository or ""
        local_value = source.removeprefix("local://")
        local_path = Path(local_value) if local_value else None
        is_local = source.startswith("local://") or bool(local_path and local_path.is_absolute())
        if workspace_override is not None:
            local_path = Path(workspace_override).resolve()
            is_local = True
        if is_local and local_path and (local_path / ".git").is_dir() and not preview_snapshot_id:
            _, commit = self.git_adapter.clone_repository(
                job_id=str(job.job_id), repo_url=str(local_path),
                revision=job.source_revision or "HEAD", pinned_commit=pinned_commit,
                workspace_dir_override=destination, access_token=None,
            )
            return commit, "local-git"
        if is_local:
            from app.services.local_source_adapter import LocalSourceAdapter

            staging_root = destination.parent / f".m-{uuid4().hex[:10]}"
            adapter = LocalSourceAdapter(workspace_base=staging_root)
            try:
                if preview_snapshot_id:
                    materialized, _ = adapter.promote_staging_to_workspace(
                        snapshot_id=preview_snapshot_id, job_id=str(job.job_id),
                        user_id=str(job.owner_user_id),
                        expected_fingerprint=snapshot_fingerprint, is_admin=True,
                    )
                else:
                    if local_path is None or not local_path.is_dir():
                        raise WorkspaceNotFoundException(
                            "The authoritative local repository source is no longer available."
                        )
                    materialized, _ = adapter.materialize_local_path(
                        local_dir=local_path, job_id=str(job.job_id),
                        expected_fingerprint=snapshot_fingerprint,
                    )
                shutil.move(str(materialized), str(destination))
            finally:
                ControlledGitAdapter._safe_rmtree(staging_root)
            return self._initialize_materialized_git(destination), "local"
        if not source:
            raise WorkspaceRecoveryFailedException(
                "Job has no authoritative repository source for staging or recovery."
            )
        _, commit = self.git_adapter.clone_repository(
            job_id=str(job.job_id), repo_url=source,
            revision=job.source_revision or "HEAD", pinned_commit=pinned_commit,
            workspace_dir_override=destination, access_token=git_token,
        )
        return commit, "git"

    @staticmethod
    def _promote(staged: Path, target: Path) -> None:
        backup = target.parent / f".b-{uuid4().hex[:10]}"
        if target.exists():
            target.rename(backup)
        try:
            staged.rename(target)
        except Exception:
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise
        ControlledGitAdapter._safe_rmtree(backup)

    async def _stage_locked(
        self,
        db: AsyncSession,
        job: Job,
        *,
        git_token: Optional[str],
        preview_snapshot_id: Optional[str],
        snapshot_fingerprint: Optional[str],
        workspace_override: Optional[Path],
        pinned_commit: Optional[str],
        correlation_id: Optional[str],
    ) -> tuple[Path, str]:
        clean_id = self._clean_job_id(job.job_id)
        target = self.get_workspace_path(job.job_id)
        staged = self.workspace_base / f".s-{clean_id[:8]}-{uuid4().hex[:10]}"
        source_identity = self._source_identity(job.source_repository)
        logger.info(
            "workspace.stage.started | job_id=%s workspace_path=%s source=%s commit=%s",
            clean_id, target, source_identity, pinned_commit,
        )
        self._audit(db, job, "WORKSPACE_STAGE_STARTED", correlation_id, {
            "workspace_path": str(target), "source": source_identity,
            "expected_commit": pinned_commit,
        })
        try:
            commit, source_type = self._materialize_source(
                job, staged, git_token=git_token,
                preview_snapshot_id=preview_snapshot_id,
                snapshot_fingerprint=snapshot_fingerprint,
                workspace_override=workspace_override, pinned_commit=pinned_commit,
            )
            if pinned_commit and pinned_commit not in {"HEAD", "LOCAL"}:
                wanted = pinned_commit.lower()
                if not (commit.lower().startswith(wanted) or wanted.startswith(commit.lower())):
                    raise WorkspaceWrongRepositoryException(
                        "Staged repository did not resolve to the authoritative snapshot commit."
                    )
            self._write_sidecar(
                staged, job_id=clean_id, source_url=job.source_repository,
                commit_sha=commit, source_type=source_type,
                source_revision=job.source_revision,
            )
            await self.validate_workspace(
                clean_id, expected_commit=pinned_commit or commit,
                expected_source=job.source_repository, workspace_path=staged,
                raise_on_error=True,
            )
            self._promote(staged, target)
            validation = await self.validate_workspace(
                clean_id, expected_commit=pinned_commit or commit,
                expected_source=job.source_repository, raise_on_error=True,
            )
        except Exception:
            ControlledGitAdapter._safe_rmtree(staged)
            raise
        self._audit(db, job, "WORKSPACE_STAGE_COMPLETED", correlation_id, {
            "workspace_path": str(target), "source": source_identity,
            "commit_sha": validation.commit_sha,
        })
        logger.info(
            "workspace.stage.completed | job_id=%s workspace_path=%s commit=%s",
            clean_id, target, validation.commit_sha,
        )
        return target, validation.commit_sha or commit

    async def stage_repository(
        self,
        db: AsyncSession,
        job: Job | UUID | str,
        source: Optional[str] = None,
        *,
        revision: Optional[str] = None,
        pinned_commit: Optional[str] = None,
        git_token: Optional[str] = None,
        preview_snapshot_id: Optional[str] = None,
        snapshot_fingerprint: Optional[str] = None,
        workspace_override: Optional[Path] = None,
        correlation_id: Optional[str] = None,
    ) -> tuple[Path, str]:
        """Stage a repository under a PostgreSQL job-row lock."""
        locked = await self._locked_job(db, job)
        if source:
            locked.source_repository = source
        if revision:
            locked.source_revision = revision
        metadata = locked.stack_metadata if isinstance(locked.stack_metadata, dict) else {}
        target_commit = pinned_commit or metadata.get("pinned_commit")
        try:
            result = await self._stage_locked(
                db, locked, git_token=git_token,
                preview_snapshot_id=preview_snapshot_id,
                snapshot_fingerprint=snapshot_fingerprint,
                workspace_override=workspace_override, pinned_commit=target_commit,
                correlation_id=correlation_id,
            )
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    async def ensure_workspace(
        self,
        db: AsyncSession,
        job: Job | UUID | str,
        *,
        git_token: Optional[str] = None,
        expected_commit: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Path:
        """Return a validated workspace, recovering it before dispatch if necessary."""
        job_obj = job if isinstance(job, Job) else await db.get(Job, UUID(str(job)))
        if job_obj is None:
            raise NotFoundException("Job", str(job))
        expected = expected_commit or await self._expected_commit(db, job_obj)
        validation = await self.validate_workspace(
            job_obj.job_id, expected_commit=expected,
            expected_source=job_obj.source_repository,
        )
        if validation.is_ready and validation.path:
            logger.info(
                "agent.dispatch.workspace_ready | job_id=%s workspace_path=%s commit=%s",
                job_obj.job_id, validation.path, validation.commit_sha,
            )
            return validation.path
        logger.warning(
            "agent.dispatch.blocked_workspace | job_id=%s workspace_path=%s code=%s reason=%s",
            job_obj.job_id, validation.path, validation.error_code,
            validation.error_message,
        )
        return await self.recover_workspace(
            db, job_obj, git_token=git_token, expected_commit=expected,
            correlation_id=correlation_id,
        )

    async def recover_workspace(
        self,
        db: AsyncSession,
        job: Job | UUID | str,
        *,
        git_token: Optional[str] = None,
        expected_commit: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Path:
        """Bounded recovery of the exact authoritative repository snapshot."""
        locked = await self._locked_job(db, job)
        expected = expected_commit or await self._expected_commit(db, locked)
        current = await self.validate_workspace(
            locked.job_id, expected_commit=expected,
            expected_source=locked.source_repository,
        )
        if current.is_ready and current.path:
            await db.commit()
            return current.path

        source_identity = self._source_identity(locked.source_repository)
        last_error: Optional[Exception] = None
        for attempt_number in range(1, self.max_recovery_attempts + 1):
            logger.warning(
                "workspace.recovery.started | job_id=%s attempt=%s workspace_path=%s commit=%s",
                locked.job_id, attempt_number,
                self.get_workspace_path(locked.job_id), expected,
            )
            self._audit(db, locked, "WORKSPACE_RECOVERY_STARTED", correlation_id, {
                "attempt": attempt_number,
                "workspace_path": str(self.get_workspace_path(locked.job_id)),
                "source": source_identity, "expected_commit": expected,
                "failure_code": current.error_code,
            })
            try:
                path, commit = await self._stage_locked(
                    db, locked, git_token=git_token,
                    preview_snapshot_id=None, snapshot_fingerprint=None,
                    workspace_override=None, pinned_commit=expected,
                    correlation_id=correlation_id,
                )
                self._audit(db, locked, "WORKSPACE_RECOVERY_COMPLETED", correlation_id, {
                    "attempt": attempt_number, "workspace_path": str(path),
                    "source": source_identity, "commit_sha": commit,
                })
                await db.commit()
                logger.info(
                    "workspace.recovery.completed | job_id=%s attempt=%s commit=%s",
                    locked.job_id, attempt_number, commit,
                )
                return path
            except Exception as exc:
                last_error = exc
                logger.exception(
                    "workspace.recovery.failed | job_id=%s attempt=%s code=%s",
                    locked.job_id, attempt_number,
                    getattr(exc, "code", type(exc).__name__),
                )
        self._audit(db, locked, "WORKSPACE_RECOVERY_FAILED", correlation_id, {
            "attempts": self.max_recovery_attempts,
            "workspace_path": str(self.get_workspace_path(locked.job_id)),
            "source": source_identity, "expected_commit": expected,
            "error_code": getattr(last_error, "code", type(last_error).__name__),
        })
        await db.commit()
        raise WorkspaceRecoveryFailedException(
            "Repository workspace could not be restored to the authoritative snapshot after "
            f"{self.max_recovery_attempts} bounded attempts: {last_error}"
        ) from last_error

    async def cleanup_workspace(
        self,
        db: AsyncSession,
        job: Job | UUID | str,
        *,
        force: bool = False,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Delete only terminal, inactive job workspaces under the same DB lock."""
        locked = await self._locked_job(db, job)
        if locked.status in NON_CLEANABLE_JOB_STATUSES or locked.status not in {
            "COMPLETED", "FAILED", "CANCELLED"
        }:
            await db.commit()
            raise ConflictException(
                f"Cannot cleanup repository workspace: job is in active state '{locked.status}'."
            )
        active_modules = list((await db.execute(
            select(Module).where(
                Module.job_id == locked.job_id,
                Module.status.in_(ACTIVE_MODULE_STATUSES),
            )
        )).scalars().all())
        active_attempts = list((await db.execute(
            select(ModuleAttempt).join(Module, Module.module_id == ModuleAttempt.module_id)
            .where(
                Module.job_id == locked.job_id,
                ModuleAttempt.status.in_(ACTIVE_ATTEMPT_STATUSES),
            )
        )).scalars().all())
        if active_modules or active_attempts:
            await db.commit()
            raise ConflictException(
                "Cannot cleanup repository workspace while module execution still requires it."
            )
        target = self.get_workspace_path(locked.job_id)
        logger.info(
            "workspace.cleanup.started | job_id=%s workspace_path=%s force=%s",
            locked.job_id, target, force,
        )
        self._audit(db, locked, "WORKSPACE_CLEANUP_STARTED", correlation_id, {
            "workspace_path": str(target), "force": force,
        })
        ControlledGitAdapter._safe_rmtree(target)
        if target.exists():
            await db.rollback()
            raise WorkspaceInvalidException(
                "Workspace cleanup did not remove the canonical directory."
            )
        self._audit(db, locked, "WORKSPACE_CLEANUP_COMPLETED", correlation_id, {
            "workspace_path": str(target), "force": force,
        })
        await db.commit()
        logger.info(
            "workspace.cleanup.completed | job_id=%s workspace_path=%s",
            locked.job_id, target,
        )
        return True


repository_workspace_service = RepositoryWorkspaceService()
