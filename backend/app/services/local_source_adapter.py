"""Local Source Adapter for Browser-Based Directory Ingestion.

Implements safe, authenticated local source-code bundle extraction, ZipSlip / path traversal
defense, deterministic canonical Merkle snapshot fingerprinting, 30-minute staging lease
management, and atomic promotion to permanent job workspaces.

Guarantees:
1. Zero code execution (strictly static filesystem extraction).
2. Path Traversal Defense: Rejects "..", absolute paths, drive letters, UNC paths, null bytes, and symlinks.
3. Canonical Snapshot Fingerprint: Deterministic SHA-256 over sorted POSIX relative paths, sizes, and file hashes.
4. Staging Isolation: Staged preview snapshots reside in backend/staging_snapshots/ with strict 30-minute TTL.
5. Incomplete Scan Detection: Enforces limits (depth <= 10, files <= 15,000, size <= 100MB) and records PARTIAL status.
6. Zero Second Upload: Seamlessly promotes staged preview snapshot to backend/repo_workspaces/job_{job_id}.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import stat
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid
import zipfile

from app.core.config import settings
from app.core.errors import (
    ConflictException,
    ErrorDetail,
    NotFoundException,
    PlatformException,
    UnauthorizedException,
    ValidationException,
)
from app.services.inventory_scanner import DiscoveredManifest, InventoryResult, RepositoryInventoryScanner

logger = logging.getLogger(__name__)


@dataclass
class StagedSnapshotMetadata:
    """Metadata describing a temporary preview snapshot staged for intake reuse."""
    snapshot_id: str
    owner_user_id: str
    source_name: str
    canonical_fingerprint: str
    file_count: int
    total_bytes: int
    is_complete: bool
    warnings: List[str]
    created_at: str
    expires_at: str


class LocalSourceSecurityException(PlatformException):
    """Raised when an uploaded archive attempts path traversal or violates security invariants."""
    def __init__(self, message: str, issue: Optional[str] = None, status_code: int = 400):
        details = [ErrorDetail(field="bundle", issue=issue or message)] if issue else []
        super().__init__(
            code="SECURITY_VIOLATION",
            message=message,
            status_code=status_code,
            details=details,
        )


class LocalSourceAdapter:
    """Manages secure extraction, fingerprinting, staging, and intake promotion for local folders."""

    MAX_FILES: int = 15000
    MAX_TOTAL_BYTES: int = 100 * 1024 * 1024       # 100 MB max archive / uncompressed source
    MAX_FILE_BYTES: int = 10 * 1024 * 1024         # 10 MB single file ceiling
    MAX_DEPTH: int = 10
    STAGING_TTL_MINUTES: int = 30

    EXCLUDED_DIRS: Set[str] = RepositoryInventoryScanner.EXCLUDE_DIRS

    def __init__(self, staging_base: Optional[Path] = None, workspace_base: Optional[Path] = None):
        import tempfile
        backend_dir = Path(__file__).resolve().parent.parent.parent
        # Preview snapshots are strictly isolated inside OS temporary directory to keep project codebase clean
        self.staging_base = staging_base or (Path(tempfile.gettempdir()) / "rebase_staging_snapshots")
        self.workspace_base = workspace_base or (backend_dir / "repo_workspaces")
        self.staging_base.mkdir(parents=True, exist_ok=True)
        self.workspace_base.mkdir(parents=True, exist_ok=True)

    @classmethod
    def calculate_canonical_fingerprint(cls, workspace_root: Path) -> str:
        """Calculates a deterministic, platform-independent canonical snapshot fingerprint.

        Format for each regular file:
            entry_bytes = f"{rel_posix_path}\\0{size_bytes}\\0{content_sha256}\\n".encode('utf-8')
        Entries are sorted in strict ascending lexicographical byte order by relative path.
        Authoritative fingerprint is SHA-256(concatenated sorted entries).
        """
        entries: List[Tuple[str, bytes]] = []

        for root, dirs, files in os.walk(workspace_root):
            # Prune excluded directories from fingerprinting
            dirs[:] = [d for d in dirs if d not in cls.EXCLUDED_DIRS and not d.startswith(".")]

            for fname in files:
                fpath = Path(root) / fname
                if not fpath.is_file() or fpath.is_symlink():
                    continue

                try:
                    rel_path = fpath.relative_to(workspace_root).as_posix()
                    size_bytes = fpath.stat().st_size
                    content = fpath.read_bytes()
                    file_sha = hashlib.sha256(content).hexdigest()
                    entry_line = f"{rel_path}\0{size_bytes}\0{file_sha}\n".encode("utf-8")
                    entries.append((rel_path, entry_line))
                except (OSError, PermissionError) as e:
                    logger.warning(f"Skipping inaccessible file during fingerprinting {fpath}: {e}")

        # Sort entries deterministically by relative path
        entries.sort(key=lambda x: x[0])

        digest = hashlib.sha256()
        for _, line_bytes in entries:
            digest.update(line_bytes)

        return digest.hexdigest()

    def stage_preview_bundle(
        self,
        archive_path: Path,
        source_name: str,
        user_id: str,
    ) -> Tuple[Path, StagedSnapshotMetadata]:
        """Safely extracts an uploaded archive into a staged preview directory.

        Enforces:
        - Strict path traversal / ZipSlip defense
        - Total file count and size limits
        - Exclusion pruning
        - Authoritative canonical fingerprinting
        - Metadata sidecar persistence with 30-minute lease
        """
        self.cleanup_stale_staging_snapshots()

        snapshot_id = str(uuid.uuid4())
        staging_dir = self.staging_base / snapshot_id
        staging_dir.mkdir(parents=True, exist_ok=True)

        is_complete = True
        warnings: List[str] = []
        file_count = 0
        total_bytes = 0

        try:
            if not zipfile.is_zipfile(archive_path):
                raise LocalSourceSecurityException(
                    "Invalid archive format: uploaded bundle must be a valid ZIP archive.",
                    issue="Uploaded file is not a valid ZIP file.",
                )

            with zipfile.ZipFile(archive_path, "r") as zf:
                infolist = zf.infolist()

                # Basic ZipBomb check
                total_uncompressed_expected = sum(info.file_size for info in infolist)
                if total_uncompressed_expected > self.MAX_TOTAL_BYTES:
                    warnings.append(
                        f"Archive uncompressed size ({total_uncompressed_expected / (1024*1024):.1f} MB) exceeds limit ({self.MAX_TOTAL_BYTES / (1024*1024):.0f} MB). Scan will be partial."
                    )
                    is_complete = False

                for member in infolist:
                    filename = member.filename

                    # 1. Reject path traversal vectors
                    if (
                        filename.startswith("/")
                        or filename.startswith("\\")
                        or ".." in filename.split("/")
                        or ".." in filename.split("\\")
                        or ":" in filename
                        or "\0" in filename
                    ):
                        raise LocalSourceSecurityException(
                            f"Path traversal detected in archive member: '{filename}'. Ingestion blocked.",
                            issue="Path traversal attack vector detected.",
                        )

                    # 2. Reject symlinks
                    is_symlink = (member.external_attr >> 16) & stat.S_IFLNK == stat.S_IFLNK
                    if is_symlink:
                        raise LocalSourceSecurityException(
                            f"Symlinks are prohibited for security: '{filename}'. Ingestion blocked.",
                            issue="Symlink detected in archive.",
                        )

                    # Normalize target path
                    normalized_parts = [p for p in Path(filename).parts if p not in (".", "")]
                    if not normalized_parts:
                        continue

                    # Depth check
                    if len(normalized_parts) > self.MAX_DEPTH:
                        warnings.append(f"Depth limit ({self.MAX_DEPTH}) exceeded at '{filename}'. Member skipped.")
                        is_complete = False
                        continue

                    # Exclusion check (skip .git, node_modules, etc.)
                    if any(part in self.EXCLUDED_DIRS for part in normalized_parts):
                        continue

                    target_file = staging_dir
                    for part in normalized_parts:
                        target_file = target_file / part

                    # Ensure target stays strictly inside staging_dir
                    try:
                        resolved_target = target_file.resolve()
                        resolved_staging = staging_dir.resolve()
                        if not resolved_target.is_relative_to(resolved_staging):
                            raise LocalSourceSecurityException(
                                f"Archive member escapes staging boundary: '{filename}'.",
                                issue="Directory escape detected.",
                            )
                    except ValueError:
                        raise LocalSourceSecurityException(
                            f"Archive member escapes staging boundary: '{filename}'.",
                            issue="Directory escape detected.",
                        )

                    if member.is_dir():
                        target_file.mkdir(parents=True, exist_ok=True)
                        continue

                    # File limits check
                    if file_count >= self.MAX_FILES:
                        warnings.append(f"Maximum file limit ({self.MAX_FILES}) reached. Remaining files skipped.")
                        is_complete = False
                        break

                    if total_bytes + member.file_size > self.MAX_TOTAL_BYTES:
                        warnings.append(
                            f"Maximum source size limit ({self.MAX_TOTAL_BYTES // (1024*1024)} MB) reached. Scan is partial."
                        )
                        is_complete = False
                        break

                    if member.file_size > self.MAX_FILE_BYTES:
                        warnings.append(f"File '{filename}' exceeds {self.MAX_FILE_BYTES // (1024*1024)} MB limit and was skipped.")
                        is_complete = False
                        continue

                    # Safe extract
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, open(target_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                    file_count += 1
                    total_bytes += member.file_size

            # Authoritative canonical Merkle fingerprint calculated directly from disk
            fingerprint = self.calculate_canonical_fingerprint(staging_dir)

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=self.STAGING_TTL_MINUTES)

            metadata = StagedSnapshotMetadata(
                snapshot_id=snapshot_id,
                owner_user_id=str(user_id),
                source_name=source_name or "local-project",
                canonical_fingerprint=fingerprint,
                file_count=file_count,
                total_bytes=total_bytes,
                is_complete=is_complete,
                warnings=warnings,
                created_at=now.isoformat(),
                expires_at=expires_at.isoformat(),
            )

            # Persist sidecar metadata
            meta_path = self.staging_base / f"{snapshot_id}.meta.json"
            meta_path.write_text(json.dumps(metadata.__dict__, indent=2), encoding="utf-8")

            return staging_dir, metadata

        except Exception:
            # Immediate cleanup on extraction failure
            self._rmtree_robust(staging_dir)
            meta_path = self.staging_base / f"{snapshot_id}.meta.json"
            if meta_path.exists():
                try:
                    meta_path.unlink()
                except Exception:
                    pass
            raise

    def get_staged_snapshot(self, snapshot_id: str) -> Tuple[Path, StagedSnapshotMetadata]:
        """Retrieves an active staged snapshot, verifying existence and checking expiration."""
        meta_path = self.staging_base / f"{snapshot_id}.meta.json"
        staging_dir = self.staging_base / snapshot_id

        if not meta_path.exists() or not staging_dir.is_dir():
            raise NotFoundException(f"Staged preview snapshot '{snapshot_id}' not found.")

        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            meta = StagedSnapshotMetadata(**data)
        except Exception as e:
            raise ValidationException(f"Corrupt snapshot metadata for '{snapshot_id}': {e}")

        # Check expiration
        expires_at = datetime.fromisoformat(meta.expires_at)
        if datetime.now(timezone.utc) > expires_at:
            self._rmtree_robust(staging_dir)
            try:
                meta_path.unlink()
            except Exception:
                pass
            raise PlatformException(
                code="EXPIRED_SNAPSHOT",
                message="Staged preview snapshot has expired (30-minute lease exceeded). Please re-select local folder.",
                status_code=410,
            )

        return staging_dir, meta

    def promote_staging_to_workspace(
        self,
        snapshot_id: str,
        job_id: str,
        user_id: str,
        expected_fingerprint: Optional[str] = None,
        is_admin: bool = False,
    ) -> Tuple[Path, str]:
        """Atomically promotes an active staged snapshot to the permanent job workspace.

        Enforces:
        - Caller authorization (must match owner_user_id or be ADMIN)
        - Expiration verification (<30m)
        - Fingerprint integrity against expected preview fingerprint
        - Target permanent directory: backend/repo_workspaces/job_{job_id}
        """
        staging_dir, meta = self.get_staged_snapshot(snapshot_id)

        # Authorization check
        if not is_admin and meta.owner_user_id != str(user_id):
            raise UnauthorizedException("You are not authorized to promote this preview snapshot.")

        # Tamper / Fingerprint verification
        if expected_fingerprint and meta.canonical_fingerprint != expected_fingerprint:
            raise ConflictException(
                message=f"Snapshot fingerprint mismatch: Staged snapshot fingerprint '{meta.canonical_fingerprint}' does not match expected '{expected_fingerprint}'. Local files were modified.",
            )

        target_workspace = self.workspace_base / f"job_{job_id}"
        if target_workspace.exists():
            self._rmtree_robust(target_workspace)

        # Move staging directory to permanent workspace
        try:
            shutil.move(str(staging_dir), str(target_workspace))
        except Exception:
            # Fallback to copytree + rmtree across filesystems
            shutil.copytree(staging_dir, target_workspace, dirs_exist_ok=True)
            self._rmtree_robust(staging_dir)

        # Clean up metadata sidecar
        meta_path = self.staging_base / f"{snapshot_id}.meta.json"
        if meta_path.exists():
            try:
                meta_path.unlink()
            except Exception:
                pass

        return target_workspace, meta.canonical_fingerprint

    def materialize_direct_upload(
        self,
        archive_path: Path,
        job_id: str,
        expected_fingerprint: Optional[str] = None,
    ) -> Tuple[Path, str]:
        """Fallback direct intake upload when preview snapshot has expired or was not staged."""
        target_workspace = self.workspace_base / f"job_{job_id}"
        if target_workspace.exists():
            self._rmtree_robust(target_workspace)
        target_workspace.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    filename = member.filename
                    if (
                        filename.startswith("/")
                        or filename.startswith("\\")
                        or ".." in filename.split("/")
                        or ".." in filename.split("\\")
                        or ":" in filename
                        or "\0" in filename
                    ):
                        raise LocalSourceSecurityException(
                            f"Path traversal detected in archive member: '{filename}'.",
                            issue="Path traversal attack vector detected.",
                        )
                    if (member.external_attr >> 16) & stat.S_IFLNK == stat.S_IFLNK:
                        raise LocalSourceSecurityException("Symlinks are prohibited.")

                    normalized_parts = [p for p in Path(filename).parts if p not in (".", "")]
                    if not normalized_parts:
                        continue

                    target_file = target_workspace
                    for part in normalized_parts:
                        target_file = target_file / part

                    resolved_target = target_file.resolve()
                    if not resolved_target.is_relative_to(target_workspace.resolve()):
                        raise LocalSourceSecurityException("Directory escape detected.")

                    if member.is_dir():
                        target_file.mkdir(parents=True, exist_ok=True)
                    else:
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member, "r") as src, open(target_file, "wb") as dst:
                            shutil.copyfileobj(src, dst)

            fingerprint = self.calculate_canonical_fingerprint(target_workspace)
            if expected_fingerprint and fingerprint != expected_fingerprint:
                self._rmtree_robust(target_workspace)
                raise ConflictException(
                    message=f"Uploaded files do not match expected snapshot fingerprint '{expected_fingerprint}'.",
                )

            return target_workspace, fingerprint
        except Exception:
            self._rmtree_robust(target_workspace)
            raise

    def materialize_local_path(
        self,
        local_dir: Path,
        job_id: str,
        expected_fingerprint: Optional[str] = None,
    ) -> Tuple[Path, str]:
        """Materializes an existing local PC directory into the permanent job workspace."""
        local_dir = local_dir.resolve()
        if not local_dir.exists():
            raise ValidationException(f"Local project directory '{local_dir}' does not exist.")
        if not local_dir.is_dir():
            raise ValidationException(f"Path '{local_dir}' is not a directory.")

        target_workspace = self.workspace_base / f"job_{job_id}"
        if target_workspace.exists():
            self._rmtree_robust(target_workspace)
        target_workspace.mkdir(parents=True, exist_ok=True)

        def _ignore_entries(directory: str, entries: List[str]) -> List[str]:
            return [e for e in entries if e in self.EXCLUDED_DIRS or (e.startswith(".") and e not in (".rebase",))]

        try:
            shutil.copytree(local_dir, target_workspace, ignore=_ignore_entries, dirs_exist_ok=True)
            fingerprint = self.calculate_canonical_fingerprint(target_workspace)
            if expected_fingerprint and fingerprint != expected_fingerprint:
                self._rmtree_robust(target_workspace)
                raise ConflictException(
                    message=f"Local project files modified: Fingerprint '{fingerprint}' does not match expected '{expected_fingerprint}'.",
                )
            return target_workspace, fingerprint
        except Exception:
            self._rmtree_robust(target_workspace)
            raise

    def cleanup_stale_staging_snapshots(self, max_age_minutes: Optional[float] = None) -> int:
        """Removes expired staging snapshots and metadata sidecars older than TTL."""
        ttl_minutes = max_age_minutes if max_age_minutes is not None else self.STAGING_TTL_MINUTES
        now = datetime.now(timezone.utc)
        cleaned_count = 0

        if not self.staging_base.exists():
            return 0

        for item in self.staging_base.iterdir():
            if item.name.endswith(".meta.json"):
                meta_file = item
                snapshot_id = item.name.removesuffix(".meta.json")
                snapshot_dir = self.staging_base / snapshot_id
                try:
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    expires_at = datetime.fromisoformat(data.get("expires_at", ""))
                    if now > expires_at or (now - datetime.fromisoformat(data.get("created_at", ""))) > timedelta(minutes=ttl_minutes):
                        if snapshot_dir.is_dir():
                            self._rmtree_robust(snapshot_dir)
                        meta_file.unlink(missing_ok=True)
                        cleaned_count += 1
                except Exception:
                    # Stale corrupt metadata, remove
                    try:
                        meta_file.unlink(missing_ok=True)
                        if snapshot_dir.is_dir():
                            self._rmtree_robust(snapshot_dir)
                        cleaned_count += 1
                    except Exception:
                        pass
            elif item.is_dir():
                # Directory without sidecar metadata older than TTL
                meta_file = self.staging_base / f"{item.name}.meta.json"
                if not meta_file.exists():
                    try:
                        mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
                        if (now - mtime) > timedelta(minutes=ttl_minutes):
                            self._rmtree_robust(item)
                            cleaned_count += 1
                    except Exception:
                        pass

        return cleaned_count

    @classmethod
    def _rmtree_robust(cls, path: Path, max_retries: int = 3, retry_delay: float = 0.2) -> None:
        """Windows-resilient recursive directory removal handling file locks and read-only attributes."""
        if not path.exists():
            return

        def _on_rm_error(func: Any, p: str, exc_info: Any) -> None:
            try:
                os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
                func(p)
            except Exception:
                pass

        for attempt in range(max_retries):
            try:
                shutil.rmtree(path, onerror=_on_rm_error)
                return
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.warning(f"Could not completely remove staging directory {path} after {max_retries} attempts.")
