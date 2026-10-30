from pathlib import Path

path = Path("backend/app/services/phase6_service.py")
text = path.read_text(encoding="utf-8")

old_snippet = """        sources = await workspace.file_snapshot(worktree)
        scopes = [
            PurePosixPath(p)
            for p in context["legacy_paths"] + context["allowed_targets"]
        ]
        source_slice = {
            p: v
            for p, v in sources.items()
            if any(
                PurePosixPath(p) == scope or scope in PurePosixPath(p).parents
                for scope in scopes
            )
        }
        if not source_slice:
            raise ValueError("Approved module legacy paths have no source evidence")"""

new_snippet = """        sources = await workspace.file_snapshot(worktree)
        scopes = [
            PurePosixPath(p)
            for p in context["legacy_paths"] + context["allowed_targets"]
        ]
        other_legacy_scopes = [
            PurePosixPath(m.legacy_path)
            for m in (
                await db.execute(
                    select(Module.legacy_path).where(
                        Module.job_id == job.job_id,
                        Module.module_id != module.module_id,
                    )
                )
            ).scalars().all()
            if m.legacy_path
        ]
        source_slice = {}
        for p, v in sources.items():
            posix_p = PurePosixPath(p)
            if posix_p.name in (
                "package-lock.json",
                "yarn.lock",
                "pnpm-lock.yaml",
                "poetry.lock",
            ):
                continue
            if not any(
                posix_p == scope or scope in posix_p.parents for scope in scopes
            ):
                continue
            if any(
                other in posix_p.parents
                and not any(other in scope.parents for scope in scopes)
                for other in other_legacy_scopes
            ):
                continue
            source_slice[p] = v
        if not source_slice:
            raise ValueError("Approved module legacy paths have no source evidence")"""

if old_snippet in text:
    text = text.replace(old_snippet, new_snippet, 1)
    path.write_text(text, encoding="utf-8")
    print("Replaced LF snippet successfully")
elif old_snippet.replace("\n", "\r\n") in text:
    text = text.replace(old_snippet.replace("\n", "\r\n"), new_snippet.replace("\n", "\r\n"), 1)
    path.write_text(text, encoding="utf-8")
    print("Replaced CRLF snippet successfully")
else:
    print("Old snippet not found!")

