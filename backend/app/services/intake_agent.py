"""Intake Agent: Safely acquires, inventories, and snapshots repository sources."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictException, ValidationException
from app.models.job import Job
from app.models.phase4 import RepositoryInventoryModel, RepositorySnapshotModel
from app.models.user import User
from app.schemas.phase4 import (
    ConfidenceLevel,
    DetectedTechnologyProfile,
    EvidenceRef,
    EvidenceType,
    FileInventoryItem,
    RepositoryInventory,
    RepositorySnapshot,
    SourceMetadata,
)
from app.services.artifact_service import ArtifactService
from app.services.evidence_service import evidence_service
from app.services.git_adapter import ControlledGitAdapter
from app.services.inventory_scanner import DiscoveredManifest, InventoryResult, RepositoryInventoryScanner
from app.services.local_source_adapter import LocalSourceAdapter
from app.services.stack_detector import StackDetector

import zipfile
import io

logger = logging.getLogger(__name__)


class IntakeSecurityError(ValueError):
    """Raised when repository archive contains security violations (ZipSlip, traversal, bomb)."""
    pass


class IntakeAgent:
    """Specialist Agent responsible for safe intake, deterministic inventory, and immutable snapshotting."""

    def __init__(
        self,
        git_adapter: Optional[ControlledGitAdapter] = None,
        local_adapter: Optional[LocalSourceAdapter] = None,
        artifact_service: Optional[ArtifactService] = None,
        max_archive_bytes: int = 50 * 1024 * 1024,
    ):
        try:
            self.git_adapter = git_adapter or ControlledGitAdapter()
            self.local_adapter = local_adapter or LocalSourceAdapter()
            self.artifact_service = artifact_service or ArtifactService()
            self.max_archive_bytes = max_archive_bytes
        except Exception as exc:
            logger.exception("IntakeAgent init failed | %s: %s", type(exc).__name__, exc)
            raise

    def extract_archive_safely(self, archive_bytes: bytes, target_dir: str | Path) -> None:
        """Safely extract zip archive guarding against ZipSlip, absolute paths, and compression bombs."""
        dest_root = Path(target_dir).resolve()
        dest_root.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > self.max_archive_bytes:
                    raise IntakeSecurityError(
                        f"Archive exceeds maximum allowed uncompressed size: {total_uncompressed} > {self.max_archive_bytes}"
                    )

                for info in zf.infolist():
                    name = info.filename
                    # Reject absolute paths (POSIX / or Windows C:\)
                    if name.startswith("/") or name.startswith("\\") or (len(name) > 1 and name[1] == ":"):
                        raise IntakeSecurityError(f"Absolute path in archive forbidden: {name}")

                    target_file = (dest_root / name).resolve()
                    if not str(target_file).startswith(str(dest_root)):
                        raise IntakeSecurityError(f"Path traversal detected in archive entry: {name}")

                    # Check for symlink targets
                    if (info.external_attr >> 16) & 0o120000 == 0o120000:
                        # Symlink detected - do not extract symlinks pointing outside target
                        continue

                    zf.extract(info, dest_root)
        except IntakeSecurityError:
            raise
        except Exception as exc:
            logger.exception("Failed extracting archive safely | %s: %s", type(exc).__name__, exc)
            raise IntakeSecurityError(f"Invalid or corrupted archive: {exc}") from exc

    def build_inventory(
        self, workspace_path: str | Path, job_id: str = "temp_intake"
    ) -> Tuple[List[FileInventoryItem], List[str], str]:
        """Convenience method returning (items, directories, inventory_hash)."""
        path = Path(workspace_path)
        inv, items, inv_hash = self.build_deterministic_inventory(path, job_id)
        return items, inv.directories, inv_hash

    def build_deterministic_inventory(
        self, workspace_path: Path, job_id: str
    ) -> Tuple[RepositoryInventory, List[FileInventoryItem], str]:
        """Scan workspace path and produce deterministic, sorted POSIX file inventory."""
        try:
            items: List[FileInventoryItem] = []
            directories: List[str] = []
            hasher = hashlib.sha256()

            # Deterministic walk excluding known ignored folders
            for root, dirs, files in os_walk_sorted(workspace_path, RepositoryInventoryScanner.EXCLUDE_DIRS):
                rel_dir = root.relative_to(workspace_path).as_posix()
                if rel_dir != ".":
                    directories.append(rel_dir)

                for filename in sorted(files):
                    file_path = root / filename
                    # Handle symlinks safely - must not escape workspace
                    if file_path.is_symlink():
                        try:
                            resolved = file_path.resolve()
                            if not str(resolved).startswith(str(workspace_path.resolve())):
                                logger.warning("Skipping symlink escaping workspace: %s", file_path)
                                continue
                        except Exception:
                            continue

                    rel_path = file_path.relative_to(workspace_path).as_posix()
                    file_size = file_path.stat().st_size if file_path.exists() else 0

                    # Compute sha256 of file content
                    file_hash = hashlib.sha256()
                    try:
                        with open(file_path, "rb") as f:
                            while chunk := f.read(65536):
                                file_hash.update(chunk)
                        digest = file_hash.hexdigest()
                    except Exception:
                        digest = hashlib.sha256(b"").hexdigest()

                    ext = file_path.suffix.lower()
                    lang = RepositoryInventoryScanner.EXTENSION_MAP.get(ext)

                    is_manifest = filename.lower() in {
                        "pom.xml", "build.gradle", "build.gradle.kts", "package.json",
                        "requirements.txt", "pyproject.toml", "gemfile", "cargo.toml",
                        "go.mod", "composer.json", "cmakelists.txt",
                    }
                    is_test = "test" in rel_path.lower() or "spec" in rel_path.lower()
                    is_config = filename.lower() in {
                        "application.properties", "application.yml", "application.yaml",
                        "settings.gradle", "tsconfig.json", "dockerfile", "docker-compose.yml",
                        "helmfile.yaml", ".env.example", ".env",
                    } or ext in {".yaml", ".yml", ".ini", ".conf", ".properties", ".env"} or "config" in filename.lower() or "env" in filename.lower()
                    is_doc = ext in {".md", ".rst", ".txt", ".adoc"}

                    item = FileInventoryItem(
                        path=rel_path,
                        size_bytes=file_size,
                        content_hash=digest,
                        language=lang,
                        is_manifest=is_manifest,
                        is_test=is_test,
                        is_config=is_config,
                        is_documentation=is_doc,
                    )
                    items.append(item)
                    hasher.update(f"{rel_path}:{file_size}:{digest}\n".encode("utf-8"))

            inventory_hash = hasher.hexdigest()
            total_bytes = sum(i.size_bytes for i in items)

            inventory = RepositoryInventory(
                inventory_id=f"inv_{uuid.uuid4().hex[:12]}",
                snapshot_id="",  # set when bound
                job_id=job_id,
                total_files=len(items),
                total_bytes=total_bytes,
                files=items,
                directories=sorted(directories),
                inventory_hash=inventory_hash,
            )
            return inventory, items, inventory_hash
        except Exception as exc:
            logger.exception("build_deterministic_inventory failed | job_id=%s | %s: %s", job_id, type(exc).__name__, exc)
            raise

    async def execute_intake(
        self,
        db: AsyncSession,
        job: Job,
        user: Optional[User] = None,
        *,
        git_token: Optional[str] = None,
        preview_snapshot_id: Optional[str] = None,
        snapshot_fingerprint: Optional[str] = None,
        workspace_override: Optional[Path] = None,
        correlation_id: Optional[str] = None,
    ) -> Tuple[RepositorySnapshot, RepositoryInventory, Dict[str, EvidenceRef]]:
        """Safely executes intake pipeline, builds inventory, snapshots metadata, and persists artifacts."""
        try:
            job_id_str = str(job.job_id)
            is_local = (job.source_repository or "").startswith("local://")

            # Check for existing latest snapshot for idempotency
            existing_snap = (
                await db.execute(
                    select(RepositorySnapshotModel)
                    .where(RepositorySnapshotModel.job_id == job.job_id)
                    .order_by(RepositorySnapshotModel.version.desc())
                )
            ).scalars().first()

            # Acquire workspace
            from app.services.job_service import JobService
            job_service = JobService(git_adapter=self.git_adapter)

            pinned_commit = None
            if isinstance(job.stack_metadata, dict):
                pinned_commit = job.stack_metadata.get("pinned_commit")

            if workspace_override is not None:
                workspace = workspace_override.resolve()
                if not workspace.is_dir():
                    raise NotFoundException("IntakeWorkspace", str(workspace))
                resolved_ref = "LOCAL"
            else:
                workspace, resolved_ref = job_service.acquire_intake_workspace(
                    job_id=job_id_str,
                    repo_url=job.source_repository,
                    revision=job.source_revision,
                    pinned_commit=pinned_commit,
                    git_token=git_token,
                    source_type="local" if is_local else "git",
                    preview_snapshot_id=preview_snapshot_id,
                    snapshot_fingerprint=snapshot_fingerprint,
                    user_id=str(user.user_id) if user else "system",
                    is_admin=True,
                )

            # Build deterministic inventory
            inventory, file_items, inventory_hash = self.build_deterministic_inventory(workspace, job_id_str)

            # If existing snapshot matches inventory hash, reuse snapshot idempotently
            if existing_snap and existing_snap.inventory_hash == inventory_hash:
                logger.info("Intake idempotent reuse | job_id=%s hash=%s", job_id_str, inventory_hash)
                existing_inv = (
                    await db.execute(
                        select(RepositoryInventoryModel)
                        .where(RepositoryInventoryModel.snapshot_id == existing_snap.snapshot_id)
                    )
                ).scalar_one_or_none()

                inventory_obj = RepositoryInventory(
                    inventory_id=str(existing_inv.inventory_id) if existing_inv else f"inv_{uuid.uuid4().hex[:12]}",
                    snapshot_id=str(existing_snap.snapshot_id),
                    job_id=job_id_str,
                    total_files=existing_snap.file_count,
                    total_bytes=existing_snap.archive_size_bytes,
                    files=[FileInventoryItem(**f) for f in (existing_inv.files_payload if existing_inv else [])],
                    directories=existing_inv.directories_payload if existing_inv else [],
                    inventory_hash=existing_snap.inventory_hash,
                )
                snapshot_obj = RepositorySnapshot(
                    snapshot_id=str(existing_snap.snapshot_id),
                    job_id=job_id_str,
                    version=existing_snap.version,
                    metadata=SourceMetadata(**existing_snap.metadata_payload),
                    tech_profile=DetectedTechnologyProfile(**existing_snap.tech_profile),
                    inventory_hash=existing_snap.inventory_hash,
                    content_hash=existing_snap.content_hash,
                )
                return snapshot_obj, inventory_obj, {}

            # Static detection of tech profile
            detected = StackDetector.detect_stack_from_workspace(
                workspace_path=workspace,
                source_name=job.name,
                source_revision=resolved_ref if not is_local else "LOCAL",
                snapshot_fingerprint=inventory_hash,
                is_complete=True,
            )

            # Convert detected stack into DetectedTechnologyProfile
            frameworks = [detected.framework] if detected.framework and detected.framework != "Generic / Undetected" else []
            b_tool = getattr(detected, "build_tool", None) or getattr(detected, "build_system", None)
            build_systems = [b_tool] if b_tool and b_tool not in ("None", "Unknown") else []
            manifests = [detected.build_file] if getattr(detected, "build_file", None) else []
            if hasattr(detected, "manifests") and detected.manifests:
                manifests.extend([getattr(m, "relative_path", str(m)) for m in detected.manifests])
            elif hasattr(detected, "components") and detected.components:
                for c in detected.components:
                    manifests.extend(c.get("manifest_files", []))

            lang_dict = {}
            if isinstance(detected.languages, dict):
                for k, v in detected.languages.items():
                    if isinstance(v, (int, float)):
                        lang_dict[k] = float(v)
                    elif isinstance(v, dict) and "percentage" in v:
                        lang_dict[k] = float(v["percentage"])
                    else:
                        lang_dict[k] = 100.0
            elif detected.primary_language:
                lang_dict[detected.primary_language] = 100.0

            tech_profile = DetectedTechnologyProfile(
                primary_language=detected.primary_language or "Unknown",
                languages=lang_dict,
                frameworks=frameworks,
                build_systems=build_systems,
                package_managers=build_systems,
                manifest_files=list(set(manifests)),
                config_files=[f.path for f in file_items if f.is_config][:20],
                test_frameworks=["JUnit" if "Java" in (detected.primary_language or "") else "pytest"] if any(f.is_test for f in file_items) else [],
                database_dialects=[],
                confidence=detected.confidence_score,
            )

            content_hasher = hashlib.sha256()
            content_hasher.update(inventory_hash.encode("utf-8"))
            content_hasher.update((resolved_ref or "").encode("utf-8"))
            overall_content_hash = content_hasher.hexdigest()

            source_metadata = SourceMetadata(
                repository_id=job_id_str,
                source_type="local" if is_local else "git",
                source_ref=job.source_repository,
                commit_sha=resolved_ref if not is_local else None,
                content_hash=overall_content_hash,
                archive_size_bytes=inventory.total_bytes,
                file_count=inventory.total_files,
                analyzer_version="4.0.0",
            )

            snapshot_id_val = uuid.uuid4()
            snapshot_obj = RepositorySnapshot(
                snapshot_id=str(snapshot_id_val),
                job_id=job_id_str,
                version=1 if not existing_snap else existing_snap.version + 1,
                metadata=source_metadata,
                tech_profile=tech_profile,
                inventory_hash=inventory_hash,
                content_hash=overall_content_hash,
            )
            inventory.snapshot_id = str(snapshot_id_val)

            # Collect initial intake evidence
            evidence_map: Dict[str, EvidenceRef] = {}
            for manifest_path in manifests:
                ev = evidence_service.create_evidence(
                    source_artifact=str(snapshot_id_val),
                    source_path=manifest_path,
                    evidence_type=EvidenceType.MANIFEST_ENTRY,
                    raw_excerpt=f"Build manifest detected: {manifest_path}",
                    confidence=ConfidenceLevel.CONFIRMED,
                    agent_name="intake-agent",
                )
                evidence_map[ev.evidence_id] = ev

            # Persist records in DB
            db_snapshot = RepositorySnapshotModel(
                snapshot_id=snapshot_id_val,
                job_id=job.job_id,
                version=snapshot_obj.version,
                source_type=source_metadata.source_type,
                source_ref=source_metadata.source_ref,
                commit_sha=source_metadata.commit_sha,
                content_hash=overall_content_hash,
                inventory_hash=inventory_hash,
                file_count=source_metadata.file_count,
                archive_size_bytes=source_metadata.archive_size_bytes,
                tech_profile=tech_profile.model_dump(),
                metadata_payload=source_metadata.model_dump(mode="json"),
            )
            db.add(db_snapshot)

            db_inventory = RepositoryInventoryModel(
                inventory_id=uuid.uuid4(),
                snapshot_id=snapshot_id_val,
                job_id=job.job_id,
                total_files=inventory.total_files,
                total_bytes=inventory.total_bytes,
                files_payload=[f.model_dump() for f in file_items],
                directories_payload=inventory.directories,
                inventory_hash=inventory_hash,
            )
            db.add(db_inventory)

            # Publish artifacts
            await self.artifact_service.create_artifact(
                db=db,
                job_id=job.job_id,
                artifact_type="RepositorySnapshot",
                version=snapshot_obj.version,
                content_bytes=json.dumps(snapshot_obj.model_dump(mode="json"), indent=2).encode("utf-8"),
                producing_agent="IntakeAgent",
                extra_metadata={"inventory_hash": inventory_hash},
                user=user,
                correlation_id=correlation_id,
            )

            await self.artifact_service.create_artifact(
                db=db,
                job_id=job.job_id,
                artifact_type="RepositoryInventory",
                version=snapshot_obj.version,
                content_bytes=json.dumps(inventory.model_dump(mode="json"), indent=2).encode("utf-8"),
                producing_agent="IntakeAgent",
                extra_metadata={"total_files": inventory.total_files},
                user=user,
                correlation_id=correlation_id,
            )

            await db.commit()
            return snapshot_obj, inventory, evidence_map
        except Exception as exc:
            logger.exception("execute_intake failed | job_id=%s | %s: %s", getattr(job, "job_id", "unknown"), type(exc).__name__, exc)
            raise


def os_walk_sorted(root_path: Path, exclude_dirs: set[str]):
    """Recursively walks directories with sorted entries and excluded directory pruning."""
    try:
        dirs_to_visit = [root_path]
        while dirs_to_visit:
            current = dirs_to_visit.pop(0)
            try:
                entries = list(current.iterdir())
            except PermissionError:
                continue
            subdirs = []
            files = []
            for e in sorted(entries, key=lambda x: x.name.lower()):
                if e.is_dir():
                    if e.name not in exclude_dirs and not e.name.startswith("."):
                        subdirs.append(e)
                elif e.is_file():
                    files.append(e.name)
            yield current, [d.name for d in subdirs], files
            dirs_to_visit.extend(subdirs)
    except Exception as exc:
        logger.exception("os_walk_sorted failed | root=%s | %s: %s", root_path, type(exc).__name__, exc)
        raise


intake_agent = IntakeAgent()
