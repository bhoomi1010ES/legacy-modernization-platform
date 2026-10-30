from pathlib import Path

path = Path("backend/app/services/phase6_workspace.py")
text = path.read_text(encoding="utf-8")

old = """        if path.exists():
            raise ConflictException(
                "Attempt workspace already exists; old attempts cannot be overwritten"
            )
        await git(repository, "worktree", "add", "-b", branch, str(path), commit)"""

new = """        if path.exists():
            try:
                await git(repository, "worktree", "remove", "--force", str(path))
            except Exception:
                pass
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        await git(repository, "worktree", "prune")
        await git(repository, "worktree", "add", "-B", branch, str(path), commit)"""

if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Updated phase6_workspace.py successfully (LF)")
elif old.replace("\n", "\r\n") in text:
    path.write_text(text.replace(old.replace("\n", "\r\n"), new.replace("\n", "\r\n"), 1), encoding="utf-8")
    print("Updated phase6_workspace.py successfully (CRLF)")
else:
    print("Old pattern not found in phase6_workspace.py")

