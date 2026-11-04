"""Deterministic integration mechanics; no model calls or host project execution."""

import json
import logging
import hashlib
import os
import stat
import zipfile
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from app.core.config import settings
from app.core.errors import ConflictException
from app.schemas.phase7 import SystemCheck
from app.services import phase6_workspace as workspace
from app.services.sandbox_protocol import validate_check_profile
from app.services.verification_profiles import get_profile
from app.services.phase5_engine import digest

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2] / "repo_workspaces" / "phase7"


def dependency_order(units: list[dict], modules: list[Any]) -> list[Any]:
    """Require the approved DAG to match runtime inventory; sort it topologically."""
    try:
        aliases = {
            key: module
            for module in modules
            for key in (str(module.module_id), module.name)
        }
        if len(units) != len(modules) or len({u["module_id"] for u in units}) != len(
            units
        ):
            raise ConflictException("Approved plan and runtime module inventory differ")
        nodes, edges = {}, {}
        for unit in units:
            module = aliases.get(unit["module_id"])
            if module is None or str(module.module_id) in nodes:
                raise ConflictException("Unknown or duplicate approved module")
            identity = str(module.module_id)
            nodes[identity] = module
            dependencies = unit.get("dependencies", [])
            if any(d not in aliases for d in dependencies):
                raise ConflictException("Approved dependency is missing from inventory")
            edges[identity] = {str(aliases[d].module_id) for d in dependencies}
            if edges[identity] != set(module.dependency_module_ids or []):
                raise ConflictException(
                    "Runtime dependencies do not match the approved DAG"
                )
        ordered, done = [], set()
        while len(done) < len(nodes):
            ready = sorted(
                key for key in nodes if key not in done and edges[key] <= done
            )
            if not ready:
                raise ConflictException("Approved integration DAG has a cycle")
            for key in ready:
                ordered.append(nodes[key])
                done.add(key)
        return ordered
    except Exception:
        logger.exception("phase7.dependency_order failed")
        raise


def system_profile(schema_required: bool, target_stack: str) -> list[dict]:
    """Load only the exact versioned system profile for this job's target stack."""
    try:
        profile=get_profile(target_stack)
        checks=[SystemCheck.model_validate(item).model_dump() for item in profile['system_checks']]
        if not validate_check_profile(checks, system=True, schema_required=schema_required):
            raise ValueError(
                "Configure real target-specific build, unit, integration, static, security, dependency, license, runtime, API compatibility, and required schema checks"
            )
        if any(item["category"] == "sbom" for item in checks):
            raise ValueError(
                "SBOM commands are selected by the configured tool, not arbitrary checks"
            )
        if settings.PHASE7_SBOM_TOOL == "syft":
            checks += [
                {"category": "sbom", "command": command}
                for command in (
                    ["syft", "version", "-o", "json"],
                    ["syft", "scan", "dir:/work", "-o", "syft-json"],
                )
            ]
        return checks
    except Exception:
        logger.exception("phase7.system_profile unavailable")
        raise


async def merge_verified(
    repo: Path, job_id: str, run_id: str, base: str, bindings: list[dict]
) -> dict:
    """Overlay exact verified ChangeSets on a fresh detached candidate; never create commits."""
    try:
        root = ROOT / run_id
        if root.exists() or root.is_symlink():
            raise ConflictException(
                "Integration workspace already exists; create a new run"
            )
        root.parent.mkdir(parents=True, exist_ok=True)
        await workspace.git(repo, "worktree", "add", "--detach", str(root), base)
        expected = await workspace.file_snapshot(root)
        history = []
        applied_paths: set[str] = set()
        for binding in bindings:
            if binding.get("source_commit") != base or binding.get("base_sha") != base:
                raise ConflictException("Verified ChangeSet is not pinned to the integration base")
            module_paths = set(binding["files"])
            collisions = applied_paths.intersection(module_paths)
            if collisions:
                return {
                    "status": "CONFLICT", "workspace": str(root),
                    "candidate_hash": None, "merge_history": history,
                    "conflicts": sorted(collisions), "blocked_module": binding["module_id"],
                    "resolution": "Revise and independently reverify overlapping module changes",
                }
            for name, content in binding["files"].items():
                target = workspace.safe_target(root, name, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            await workspace.git(root, "add", "--", *sorted(module_paths))
            changed = set(filter(None, (await workspace.git(root, "diff", "--cached", "--name-only", "-z")).split("\x00")))
            if changed != applied_paths.union(module_paths):
                raise ConflictException("Candidate staged paths differ from verified ChangeSets")
            applied_paths.update(module_paths)
            expected.update(binding["files"])
            actual = await workspace.file_snapshot(root)
            if actual != expected:
                raise ConflictException(
                    "Merged tree differs from exact verified module changes; integration blocked"
                )
            history.append(
                {
                    key: binding[key]
                    for key in ("module_id", "attempt_id", "base_sha", "diff_hash", "code_hash")
                }
            )
        diff = await workspace.git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv")
        # Bind the integrated candidate to its pinned base and the complete
        # tracked file map; a diff-only hash could collide across source bases.
        tree_hash = digest({"base_sha": base, "files": expected})
        return {
            "status": "MERGED",
            "workspace": str(root),
            "base_sha": base,
            "candidate_hash": tree_hash,
            "merge_history": history,
            "conflicts": [],
            "files": expected,
            "diff": diff,
        }
    except Exception:
        logger.exception("phase7.merge_verified failed | run_id=%s", run_id)
        raise


def package_project(root: Path, tracked_files: list[str] | None = None) -> tuple[bytes, list[str]]:
    """Build a safe ZIP from the verified candidate tree, excluding platform controls and secrets."""
    from app.services.secret_redactor import get_secret_redactor

    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Packaging root must be a directory")
    excluded = {".git", ".hg", ".svn", ".env", ".agents", ".codex", ".aws", ".azure", ".ssh", "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv", "tmp", "temp"}
    excluded_files = {".rebase_workspace.json", ".dockerconfigjson", ".npmrc", ".pypirc", ".netrc", ".git-credentials", "id_rsa", "id_ed25519", "credentials", "secrets.json"}
    secret_suffixes = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
    def excluded_name(name: str) -> bool:
        lowered = name.lower()
        return lowered in excluded_files or lowered.endswith(tuple(secret_suffixes))
    redactor = get_secret_redactor()
    check_secret = getattr(redactor, "has_secret_material", lambda value: redactor.redact_text(value) != value)
    output = BytesIO()
    names: list[str] = []
    pending_files: list[tuple[str, bytes]] = []
    normalized_names: set[str] = set()
    tracked = set(tracked_files) if tracked_files is not None else None
    total = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept = []
            for dirname in dirs:
                item = current_path / dirname
                if dirname.lower() in excluded or dirname.lower().startswith(".env"):
                    continue
                if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
                    raise ValueError("ZIP packaging rejects symlinks and junctions")
                kept.append(dirname)
            dirs[:] = sorted(kept)
            for filename in sorted(files):
                item = current_path / filename
                rel = item.relative_to(root).as_posix()
                if tracked is not None and rel not in tracked:
                    continue
                parts = PurePosixPath(rel).parts
                if any(part.lower() in excluded or part.lower().startswith(".env") for part in parts):
                    continue
                if excluded_name(filename):
                    continue
                if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
                    raise ValueError("ZIP packaging rejects symlinks and junctions")
                info = item.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("ZIP packaging accepts regular files only")
                if PurePosixPath(rel).is_absolute() or ".." in parts or "\\" in rel or ":" in rel or "\x00" in rel or any(part in {"", "."} or part.rstrip(" .") != part or part.split(".", 1)[0].lower() in {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))} for part in parts):
                    raise ValueError("Unsafe ZIP path")
                if rel.casefold() in normalized_names:
                    raise ValueError("ZIP contains case-colliding paths")
                normalized_names.add(rel.casefold())
                if len(pending_files) >= 50000:
                    raise ValueError("Project exceeds ZIP entry limit")
                data = item.read_bytes()
                total += len(data)
                if total > 512 * 1024 * 1024:
                    raise ValueError("Project exceeds ZIP size limit")
                text = data.decode("utf-8", errors="replace")
                if check_secret(text):
                    raise ValueError(f"Secret material found in project file: {rel}")
                pending_files.append((rel, data))
        for rel, data in sorted(pending_files, key=lambda entry: entry[0]):
            archive.writestr(rel, data)
            names.append(rel)
    if tracked is not None:
        expected = {
            name for name in tracked
            if not any(part.lower() in excluded or part.lower().startswith(".env") for part in PurePosixPath(name).parts)
            and not excluded_name(PurePosixPath(name).name)
        }
        if set(names) != expected:
            raise ValueError("Tracked candidate files are missing or unsafe during ZIP packaging")
    payload = output.getvalue()
    with zipfile.ZipFile(BytesIO(payload), "r") as check:
        bad = check.testzip()
        if bad:
            raise ValueError(f"ZIP integrity check failed at {bad}")
        if check.namelist() != names:
            raise ValueError("ZIP entry inventory mismatch")
    return payload, names


async def cleanup_candidate(repo: Path, candidate: str | Path) -> None:
    """Remove only a phase-7 registered worktree under its dedicated root."""
    target = Path(candidate)
    root = ROOT.resolve()
    resolved_parent = target.parent.resolve()
    if resolved_parent != root or target.name in {"", ".", ".."} or target.is_symlink():
        raise ValueError("Refusing unsafe integration workspace cleanup target")
    if target.exists():
        await workspace.git(repo, "worktree", "remove", "--force", str(target))
    await workspace.git(repo, "worktree", "prune")


def sbom_evidence(verification: dict, files: dict[str, str]) -> dict:
    """Record actual Syft-native JSON; never claim SPDX/CycloneDX or an unexecuted tool."""
    try:
        tool = settings.PHASE7_SBOM_TOOL
        if not tool:
            return {
                "status": "BLOCKED",
                "reason": "No SBOM tool deliberately selected",
                "tool": None,
                "format": None,
            }
        if tool != "syft":
            return {
                "status": "NOT_RUN",
                "reason": "Configured SBOM tool is unsupported",
                "tool": tool,
                "format": None,
            }
        checks = [
            check
            for check in verification.get("checks", [])
            if check["category"] == "sbom"
        ]
        if len(checks) != 2 or any(
            check.get("exit_code") != 0 or check.get("status") != "PASS"
            for check in checks
        ):
            return {
                "status": "BLOCKED",
                "reason": "Syft version/scan did not execute successfully in the sandbox",
                "tool": tool,
                "format": None,
            }
        version, document = json.loads(checks[0].get("stdout", "")), json.loads(
            checks[1].get("stdout", "")
        )
        if (
            not isinstance(version.get("version"), str)
            or not version["version"]
            or document.get("descriptor", {}).get("name") != "syft"
            or document["descriptor"].get("version") != version["version"]
            or not isinstance(document.get("artifacts"), list)
        ):
            raise ValueError("SBOM identity/output contract is invalid")
        limitations = [
            "Syft-native JSON; not claimed as SPDX or CycloneDX. No online vulnerability audit was performed."
        ]
        ecosystems = [
            name
            for name in files
            if name.endswith(
                (".csproj", "pom.xml", "build.gradle", "Cargo.toml", "go.mod")
            )
        ]
        if ecosystems:
            limitations.append(
                "Non-Python/npm ecosystems require explicit review of generator support: "
                + ", ".join(ecosystems)
            )
        return {
            "status": "GENERATED",
            "tool": "syft",
            "tool_version": version["version"],
            "format": "syft-json",
            "component_count": len(document["artifacts"]),
            "limitations": limitations,
            "document": document,
        }
    except (ValueError, TypeError, KeyError):
        logger.exception("phase7.sbom_evidence invalid or truncated")
        return {
            "status": "INVALID",
            "reason": "SBOM output invalid, truncated or identity mismatch",
            "tool": "syft",
            "format": None,
        }
    except Exception:
        logger.exception("phase7.sbom_evidence failed")
        raise
