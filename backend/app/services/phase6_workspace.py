"""Isolated Git worktrees and strict module paths. Never execute repository code on host."""

import asyncio
import os
import re
from pathlib import Path, PurePosixPath
from app.core.errors import ConflictException
from app.services.repository_workspace_service import repository_workspace_service
import logging

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2] / "repo_workspaces" / "phase6"


def safe_target(root: Path, relative: str, allowed: str) -> Path:
    try:
        if "\\" in relative or ":" in relative or "\x00" in relative:
            raise ValueError("Only repository-relative POSIX paths are allowed")
        parts = PurePosixPath(relative).parts
        permitted = PurePosixPath(allowed)
        if (
            not parts
            or relative.startswith("/")
            or any(
                p.lower() in {"..", ".git", "node_modules", ".env", ".agents", ".codex"}
                for p in parts
            )
        ):
            raise ValueError("Unsafe target path")
        if any(
            p.lower() in {"tests", "test", "characterization", "fixtures"}
            or p.lower().startswith(("test_", ".env"))
            or p.lower().endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js"))
            for p in parts
        ):
            raise ValueError(
                "CodeWriter cannot edit test/fixture/configuration evidence"
            )
        path = PurePosixPath(relative)
        if path.name.lower() in {
            "conftest.py",
            "pytest.ini",
            "pyproject.toml",
            "setup.cfg",
            "setup.py",
            "tox.ini",
            "package.json",
            "package-lock.json",
            "yarn.lock",
            "pnpm-lock.yaml",
            ".gitattributes",
            ".gitmodules",
        } or path.name.lower().startswith(("tsconfig", "eslint", ".eslintrc")):
            raise ValueError(
                "CodeWriter cannot edit execution policy or package configuration"
            )
        if path != permitted and (permitted.suffix or permitted not in path.parents):
            raise ValueError("Path is outside the approved module target")
        for parent in (root / relative, *(root / relative).parents):
            if parent == root.parent:
                break
            if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
                raise ValueError("Symlinks and junctions are prohibited")
        result = (root / relative).resolve()
        if root.resolve() not in result.parents:
            raise ValueError("Path escapes isolated worktree")
        return result
    except Exception:
        logger.exception("phase6.safe_target failed")
        raise


async def git(repository: Path, *args: str) -> str:
    try:
        # No provider/cloud credentials or repository-configured host executables.
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP"}
        }
        gitdir = repository / ".git"
        if gitdir.is_file():
            pointer = gitdir.read_text(encoding="utf-8").strip()
            gitdir = Path(pointer.removeprefix("gitdir: "))
        config = (
            gitdir / "config"
            if (gitdir / "config").is_file()
            else gitdir.parent.parent / "config"
        )
        if config.is_file() and re.search(
            r"(?im)^\s*\[\s*(filter|include|includeIf|merge|diff)\b",
            config.read_text(encoding="utf-8"),
        ):
            raise ValueError(
                "Local Git filters/includes are prohibited in isolated workspaces"
            )
        env.update(
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_AUTHOR_NAME="Rebase",
            GIT_AUTHOR_EMAIL="rebase@example.invalid",
            GIT_COMMITTER_NAME="Rebase",
            GIT_COMMITTER_EMAIL="rebase@example.invalid",
        )
        cmd = [
            "git",
            "-c",
            "safe.directory=*",
            "-c",
            f"core.hooksPath={os.devnull}",
            "-c",
            "core.longpaths=true",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "submodule.recurse=false",
            "-C",
            str(repository),
            *args,
        ]
        from app.core.subprocesses import run_subprocess_async

        try:
            res = await run_subprocess_async(cmd, env=env, timeout=30.0)
        except asyncio.TimeoutError:
            raise ConflictException("Git workspace operation timed out")
        if res.returncode:
            err_msg = res.stderr.decode("utf-8", errors="replace").strip() if res.stderr else ""
            logger.error("Git workspace operation failed with rc %s: %s", res.returncode, err_msg)
            raise ConflictException(
                f"Git workspace operation failed: {err_msg or 'ensure a pinned, staged Git repository is available'}"
            )
        return res.stdout.decode("utf-8", errors="replace").strip()
    except Exception:
        logger.exception("phase6.git failed")
        raise


def repository_for(job_id: str) -> Path:
    try:
        from app.core.errors import WorkspaceNotFoundException

        authoritative = repository_workspace_service.get_workspace_path(job_id)
        if (
            authoritative.is_dir()
            and (authoritative / ".git").exists()
            and (authoritative / ".rebase_workspace.json").is_file()
            and not (authoritative / ".git").is_symlink()
            and not authoritative.is_symlink()
            and not getattr(authoritative, "is_junction", lambda: False)()
        ):
            return authoritative.resolve()
        raise WorkspaceNotFoundException(
            "Staged Git repository unavailable; conversion is blocked"
        )
    except Exception:
        logger.exception("phase6.repository_for failed | job_id=%s", job_id)
        raise


async def prepare(
    repository: Path,
    job_id: str,
    module_id: str,
    attempt_id: str,
    number: int,
    commit: str,
) -> tuple[Path, str]:
    try:
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
            raise ValueError("An exact pinned source commit is required")
        # UUID attempt ownership is globally unique. A flat layout avoids Git for
        # Windows' internal GIT_DIR limit without sharing any writable workspace.
        path = ROOT / attempt_id
        path.parent.mkdir(parents=True, exist_ok=True)
        branch = f"job/{job_id}/module/{module_id}/attempt/{number}"
        try:
            wt_list = await git(repository, "worktree", "list", "--porcelain")
            current_wt_dir = None
            for wt_line in wt_list.splitlines():
                if wt_line.startswith("worktree "):
                    current_wt_dir = wt_line.split(" ", 1)[1].strip()
                elif wt_line.startswith("branch "):
                    b_ref = wt_line.split(" ", 1)[1].strip()
                    if b_ref == f"refs/heads/{branch}" and current_wt_dir and current_wt_dir != str(path):
                        try:
                            await git(repository, "worktree", "remove", "--force", current_wt_dir)
                        except Exception:
                            pass
        except Exception:
            pass
        if path.exists():
            try:
                await git(repository, "worktree", "remove", "--force", str(path))
            except Exception:
                pass
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        await git(repository, "worktree", "prune")
        await git(repository, "worktree", "add", "-B", branch, str(path), commit)
        return path, branch
    except Exception:
        logger.exception("phase6.prepare failed | attempt_id=%s", attempt_id)
        raise


async def apply_changes(
    worktree: Path, files: dict[str, str], allowed: str | list[str]
) -> dict:
    try:
        if sum(len(v.encode()) for v in files.values()) > 1048576:
            raise ValueError("ChangeSet exceeds 1 MiB")
        scopes = [allowed] if isinstance(allowed, str) else allowed
        targets = {}
        for name in files:
            matches = [
                scope
                for scope in scopes
                if PurePosixPath(name) == PurePosixPath(scope)
                or (
                    not PurePosixPath(scope).suffix
                    and PurePosixPath(scope) in PurePosixPath(name).parents
                )
            ]
            if not matches:
                raise ValueError("Path is outside every approved module target")
            targets[name] = safe_target(worktree, name, matches[0])
        for relative, path in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            content = files[relative]
            if isinstance(content, str) and ";base64," in content and content.startswith("data:"):
                import base64
                b64_str = content.split(";base64,", 1)[1]
                path.write_bytes(base64.b64decode(b64_str))
            else:
                if isinstance(content, str) and "\x00" in content:
                    content = content.replace("\x00", "")
                path.write_text(content, encoding="utf-8", newline="\n")
        await git(worktree, "add", "--", *targets)
        diff = await git(worktree, "diff", "--cached", "--no-ext-diff", "--no-textconv")
        await git(
            worktree, "commit", "--allow-empty", "-m", "Module conversion attempt"
        )
        return {
            "diff": diff,
            "changed_files": list(files),
            "commit": await git(worktree, "rev-parse", "HEAD"),
        }
    except Exception:
        logger.exception("phase6.apply_changes failed")
        raise


async def file_snapshot(worktree: Path) -> dict[str, str]:
    """Send tracked files only; no .git, host environment, secrets or mutable mounts."""
    try:
        from app.services.secret_redactor import get_secret_redactor

        tracked = (await git(worktree, "ls-files", "-z")).split("\x00")
        files = {}
        size = 0
        for name in tracked:
            if not name or any(
                p in {".git", ".env", "node_modules", ".agents", ".codex"}
                or p.startswith(".env.")
                for p in PurePosixPath(name).parts
            ):
                continue
            path = worktree / name
            if (
                path.is_symlink()
                or not path.is_file()
                or worktree.resolve() not in path.resolve().parents
            ):
                raise ValueError("Unsafe tracked file in verification workspace")
            size += path.stat().st_size
            if size > 8 * 1048576:
                raise ValueError("Verification workspace exceeds 8 MiB adapter limit")
            try:
                data = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                import hashlib
                raw_bytes = path.read_bytes()
                digest = hashlib.sha256(raw_bytes).hexdigest()
                data = f"[binary asset: {len(raw_bytes)} bytes, sha256:{digest}]"
            redactor = get_secret_redactor()
            check_fn = getattr(redactor, "has_secret_material", lambda t: redactor.redact_text(t) != t)
            if check_fn(data):
                raise ValueError("Secret material found in verification workspace")
            files[name] = data
        return files
    except Exception:
        logger.exception("phase6.file_snapshot failed")
        raise
