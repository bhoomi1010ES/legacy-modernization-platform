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
_WINDOWS_DEVICE_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
_FORBIDDEN_COMPONENTS = {
    ".git", ".hg", ".svn", ".env", ".agents", ".codex", "node_modules",
    ".ssh", ".aws", ".azure", ".config", "docker.sock",
}


def safe_target(root: Path, relative: str, allowed: str) -> Path:
    try:
        if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative or "\x00" in relative:
            raise ValueError("Only repository-relative POSIX paths are allowed")
        if relative.startswith("/") or relative.startswith("//"):
            raise ValueError("Absolute paths are prohibited")
        parts = PurePosixPath(relative).parts
        if PurePosixPath(relative).as_posix() != relative:
            raise ValueError("Path must use canonical normalized POSIX form")
        permitted = PurePosixPath(allowed)
        if (
            not parts
            or any(
                p in {"", ".", ".."}
                or p.lower() in _FORBIDDEN_COMPONENTS
                or p.rstrip(" .").split(".", 1)[0].lower() in _WINDOWS_DEVICE_NAMES
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
        if any(p.startswith(".") for p in parts):
            raise ValueError("Hidden control and configuration files are prohibited")
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
        root = root.resolve()
        candidate = root.joinpath(*parts)
        for parent in (candidate, *candidate.parents):
            if parent == root:
                break
            if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
                raise ValueError("Symlinks and junctions are prohibited")
        result = candidate.resolve()
        if root not in result.parents:
            raise ValueError("Path escapes isolated worktree")
        return result
    except Exception:
        logger.exception("phase6.safe_target failed")
        raise


async def git(repository: Path, *args: str) -> str:
    if any(arg == 'commit' or (isinstance(arg, str) and arg.strip() == 'commit') for arg in args):
        gitdir = repository / '.git'
        if gitdir.is_file():
            raise ConflictException('Git commit operations are forbidden during conversion and integration')
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
    worktree: Path,
    files: dict[str, str],
    allowed: str | list[str],
    *,
    expected_staged_files: set[str] | None = None,
) -> dict:
    try:
        if not isinstance(files, dict) or not files or any(
            not isinstance(name, str) or not isinstance(content, str)
            for name, content in files.items()
        ):
            raise ValueError("ChangeSet files must be a non-empty map of text paths")
        if sum(len(v.encode("utf-8")) for v in files.values()) > 1048576:
            raise ValueError("ChangeSet exceeds 1 MiB")
        if any("\x00" in v for v in files.values()):
            raise ValueError("NUL bytes are prohibited in generated text files")
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
        staged_before = set(filter(None, (await git(worktree, "diff", "--cached", "--name-only", "-z")).split("\x00")))
        if expected_staged_files is None:
            expected_staged_files = set()
        if staged_before != expected_staged_files:
            raise ValueError("Pre-existing staged files differ from validated attempt evidence")
        if set(targets).intersection(staged_before):
            raise ValueError("ChangeSet overlaps an already validated staged dependency")
        for relative, path in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            content = files[relative]
            path.write_text(content, encoding="utf-8", newline="\n")
        await git(worktree, "add", "--", *targets)
        diff = await git(worktree, "diff", "--cached", "--no-ext-diff", "--no-textconv")
        changed = (await git(worktree, "diff", "--cached", "--name-only", "-z")).split("\x00")
        if set(filter(None, changed)) != staged_before | set(targets):
            raise ValueError("Staged repository changes differ from validated attempt evidence")
        if any(name == ".gitmodules" or name.startswith(".git/") for name in changed):
            raise ValueError("Repository metadata modifications are prohibited")
        base_sha = await git(worktree, "rev-parse", "HEAD")
        # The staged Git tree is a stable identity for the full candidate without
        # creating a conversion-time commit. Verification binds this tree hash and
        # the pinned source base SHA as a pair.
        candidate_hash = await git(worktree, "write-tree")
        if await git(worktree, "rev-parse", "HEAD") != base_sha:
            raise ValueError("Candidate application changed the pinned source HEAD")
        import hashlib
        return {
            "diff": diff,
            "diff_hash": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            "changed_files": list(files),
            "base_sha": base_sha,
            "candidate_hash": candidate_hash,
            "staged_files": sorted(staged_before | set(targets)),
        }
    except Exception:
        logger.exception("phase6.apply_changes failed")
        raise


async def file_snapshot(
    worktree: Path, *, exclude_paths: set[str] | frozenset[str] = frozenset()
) -> dict[str, str]:
    """Send tracked files only, with only explicitly named exclusions.

    Callers that omit generated executables must record their hashes and reason
    in the evidence binding. Exclusions are exact canonical tracked paths; this
    does not change the default snapshot contract used by other phases.
    """
    try:
        from app.services.secret_redactor import get_secret_redactor

        for name in exclude_paths:
            if (
                not isinstance(name, str)
                or not name
                or PurePosixPath(name).as_posix() != name
                or PurePosixPath(name).is_absolute()
                or any(part in {".", ".."} for part in PurePosixPath(name).parts)
            ):
                raise ValueError("Invalid exact snapshot exclusion path")
        tracked = (await git(worktree, "ls-files", "-z")).split("\x00")
        tracked_names = {name for name in tracked if name}
        root = worktree.resolve()
        for name in exclude_paths:
            if name not in tracked_names:
                raise ValueError("Snapshot exclusion must name an exact tracked file")
            excluded_path = worktree / name
            if (
                excluded_path.is_symlink()
                or getattr(excluded_path, "is_junction", lambda: False)()
                or not excluded_path.is_file()
                or root not in excluded_path.resolve().parents
            ):
                raise ValueError("Unsafe exact snapshot exclusion file")
        files = {}
        size = 0
        for name in tracked:
            if not name or name in exclude_paths or any(
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
                import base64
                data = {"encoding": "base64", "data": base64.b64encode(raw_bytes).decode("ascii"), "sha256": digest}
            redactor = get_secret_redactor()
            check_fn = getattr(redactor, "has_secret_material", lambda t: redactor.redact_text(t) != t)
            if isinstance(data, str) and check_fn(data):
                raise ValueError("Secret material found in verification workspace")
            files[name] = data
        return files
    except Exception:
        logger.exception("phase6.file_snapshot failed")
        raise
