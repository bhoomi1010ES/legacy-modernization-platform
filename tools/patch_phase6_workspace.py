from pathlib import Path

target = """        path = ROOT / attempt_id
        path.parent.mkdir(parents=True, exist_ok=True)
        branch = f"job/{job_id}/module/{module_id}/attempt/{number}"
        if path.exists():
            try:
                await git(repository, "worktree", "remove", "--force", str(path))
            except Exception:
                pass
            import shutil
            shutil.rmtree(path, ignore_errors=True)
        await git(repository, "worktree", "prune")
        await git(repository, "worktree", "add", "-B", branch, str(path), commit)
        return path, branch"""

replacement = """        path = ROOT / attempt_id
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
        return path, branch"""

file_path = Path("backend/app/services/phase6_workspace.py")
content = file_path.read_text(encoding="utf-8")
normalized_content = content.replace("\r\n", "\n")
normalized_target = target.replace("\r\n", "\n")
normalized_replacement = replacement.replace("\r\n", "\n")

assert normalized_target in normalized_content, "Target not found in file!"
updated = normalized_content.replace(normalized_target, normalized_replacement)
file_path.write_text(updated, encoding="utf-8", newline="\n")
print("Successfully patched phase6_workspace.py")

