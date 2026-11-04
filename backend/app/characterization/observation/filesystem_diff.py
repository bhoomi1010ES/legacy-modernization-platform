"""Filesystem snapshot capture and SHA-256 mutation differ."""

import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple

from app.characterization.contracts.observations import StateChange


class FilesystemDiffer:
    """Computes SHA-256 tree snapshots to capture filesystem mutations deterministically."""

    def capture_snapshot(self, directory: Path) -> Dict[str, str]:
        """Capture mapping of relative POSIX path to SHA-256 content hash."""
        snapshot: Dict[str, str] = {}
        if not directory.exists():
            return snapshot

        for file_path in sorted(directory.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(directory).as_posix()
            if any(part in {".git", "node_modules", ".venv"} for part in rel.split("/")):
                continue
            try:
                b = file_path.read_bytes()
                snapshot[rel] = hashlib.sha256(b).hexdigest()
            except Exception:
                continue

        return snapshot

    def diff(
        self,
        before: Dict[str, str],
        after: Dict[str, str],
    ) -> Tuple[List[str], List[str], List[str], List[StateChange]]:
        """Compute created, modified, and deleted files and construct StateChange objects."""
        before_keys: Set[str] = set(before)
        after_keys: Set[str] = set(after)

        created = sorted(list(after_keys - before_keys))
        deleted = sorted(list(before_keys - after_keys))
        modified = sorted([
            k for k in (before_keys & after_keys)
            if before[k] != after[k]
        ])

        changes: List[StateChange] = []
        for path in created:
            changes.append(
                StateChange(
                    change_type="FILE_CREATED",
                    target=path,
                    details={"path": path},
                    after_hash=after[path],
                )
            )
        for path in modified:
            changes.append(
                StateChange(
                    change_type="FILE_MODIFIED",
                    target=path,
                    details={"path": path},
                    before_hash=before[path],
                    after_hash=after[path],
                )
            )
        for path in deleted:
            changes.append(
                StateChange(
                    change_type="FILE_DELETED",
                    target=path,
                    details={"path": path},
                    before_hash=before[path],
                )
            )

        return created, modified, deleted, changes

