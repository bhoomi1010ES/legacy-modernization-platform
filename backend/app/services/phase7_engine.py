"""Deterministic integration mechanics; no model calls or host project execution."""

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.errors import ConflictException
from app.schemas.phase7 import SystemCheck
from app.services import phase6_workspace as workspace
from app.services.phase6_sandbox import approved_command

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


def system_profile(schema_required: bool) -> list[dict]:
    """Only administrator configuration selects commands; callers supply no argv."""
    try:
        checks = [
            SystemCheck.model_validate(item).model_dump()
            for item in json.loads(settings.PHASE7_CHECK_COMMANDS_JSON)
        ]
        required = {"build", "unit", "integration", "static", "security"} | (
            {"schema"} if schema_required else set()
        )
        if not required <= {item["category"] for item in checks} or any(
            not approved_command(item["command"]) for item in checks
        ):
            raise ValueError(
                "Configure meaningful full-system build/unit/integration/static/security and required schema checks"
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
    """Merge exact verified commits in a fresh candidate branch; conflicts require revision."""
    try:
        root = ROOT / run_id
        if root.exists() or root.is_symlink():
            raise ConflictException(
                "Integration workspace already exists; create a new run"
            )
        root.parent.mkdir(parents=True, exist_ok=True)
        branch = f"job/{job_id}/integration/{run_id}"
        await workspace.git(repo, "worktree", "add", "-b", branch, str(root), base)
        expected = await workspace.file_snapshot(root)
        history = []
        for binding in bindings:
            canonical_branch = f"job/{job_id}/module/{binding['module_id']}/attempt/{binding['attempt_number']}"
            if (
                binding["branch"] != canonical_branch
                or await workspace.git(repo, "rev-parse", binding["branch"])
                != binding["commit"]
            ):
                raise ConflictException(
                    "Verified module branch moved or has invalid ownership"
                )
            await workspace.git(
                repo, "merge-base", "--is-ancestor", base, binding["commit"]
            )
            try:
                await workspace.git(
                    root, "merge", "--no-ff", "--no-edit", binding["commit"]
                )
            except ConflictException:
                conflicts = (
                    await workspace.git(root, "diff", "--name-only", "--diff-filter=U")
                ).splitlines()
                if not conflicts:
                    raise
                await workspace.git(root, "merge", "--abort")
                return {
                    "status": "CONFLICT",
                    "branch": branch,
                    "workspace": str(root),
                    "commit": await workspace.git(root, "rev-parse", "HEAD"),
                    "merge_history": history,
                    "conflicts": conflicts,
                    "blocked_module": binding["module_id"],
                    "resolution": "Revise and independently reverify the conflicting module changes; no automatic conflict resolution or discarded changes",
                }
            expected.update(binding["files"])
            actual = await workspace.file_snapshot(root)
            if actual != expected:
                raise ConflictException(
                    "Merged tree differs from exact verified module changes; integration blocked"
                )
            history.append(
                {
                    key: binding[key]
                    for key in (
                        "module_id",
                        "attempt_id",
                        "commit",
                        "branch",
                        "code_hash",
                    )
                }
            )
        return {
            "status": "MERGED",
            "branch": branch,
            "workspace": str(root),
            "commit": await workspace.git(root, "rev-parse", "HEAD"),
            "merge_history": history,
            "conflicts": [],
            "files": expected,
            "diff": await workspace.git(
                root, "diff", "--no-ext-diff", "--no-textconv", base, "HEAD"
            ),
        }
    except Exception:
        logger.exception("phase7.merge_verified failed | run_id=%s", run_id)
        raise


def sbom_evidence(verification: dict, files: dict[str, str]) -> dict:
    """Record actual Syft-native JSON; never claim SPDX/CycloneDX or an unexecuted tool."""
    try:
        tool = settings.PHASE7_SBOM_TOOL
        if not tool:
            return {
                "status": "UNAVAILABLE",
                "reason": "No SBOM tool deliberately selected",
                "tool": None,
                "format": None,
            }
        if tool != "syft":
            return {
                "status": "UNSUPPORTED",
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
                "status": "UNAVAILABLE",
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
