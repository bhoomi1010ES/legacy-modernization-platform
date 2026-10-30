from pathlib import Path

def patch_file(path_str: str, target: str, replacement: str):
    path = Path(path_str)
    content = path.read_text(encoding="utf-8")
    # Normalize line endings to test target
    normalized_content = content.replace("\r\n", "\n")
    normalized_target = target.replace("\r\n", "\n")
    normalized_replacement = replacement.replace("\r\n", "\n")
    
    if normalized_target not in normalized_content:
        print(f"Target not found in {path_str}")
        return False
        
    new_content = normalized_content.replace(normalized_target, normalized_replacement, 1)
    # preserve CRLF if original had CRLF
    if "\r\n" in content:
        new_content = new_content.replace("\n", "\r\n")
    path.write_text(new_content, encoding="utf-8")
    print(f"Successfully patched {path_str}")
    return True

# 1. phase6_workspace.py
p6_target = """        process = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            f"core.hooksPath={os.devnull}","""

p6_replacement = """        process = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            "safe.directory=*",
            "-c",
            f"core.hooksPath={os.devnull}","""

patch_file("backend/app/services/phase6_workspace.py", p6_target, p6_replacement)

# Also patch error reporting in phase6_workspace.py if returncode
p6_err_target = """        if process.returncode:
            raise ConflictException(
                "Git workspace operation failed; ensure a pinned, staged Git repository is available"
            )"""

p6_err_replacement = """        if process.returncode:
            err_msg = error.decode("utf-8", errors="replace").strip() if error else ""
            logger.error("Git workspace operation failed with rc %s: %s", process.returncode, err_msg)
            raise ConflictException(
                f"Git workspace operation failed: {err_msg or 'ensure a pinned, staged Git repository is available'}"
            )"""

patch_file("backend/app/services/phase6_workspace.py", p6_err_target, p6_err_replacement)

# 2. git_adapter.py
ga_target = """        safe_args = [
            "git",
            "-c", "credential.helper=",             # Never reuse host credentials
            "-c", "core.hooksPath=/dev/null",       # Disable git hooks to prevent code execution"""

ga_replacement = """        safe_args = [
            "git",
            "-c", "safe.directory=*",               # Allow local workspaces regardless of owner
            "-c", "credential.helper=",             # Never reuse host credentials
            "-c", "core.hooksPath=/dev/null",       # Disable git hooks to prevent code execution"""

patch_file("backend/app/services/git_adapter.py", ga_target, ga_replacement)

