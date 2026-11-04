from pathlib import Path

p = Path("backend/app/api/v1/jobs.py")
text = p.read_text(encoding="utf-8")

old_part = """        resolved_lower = str(local_dir).lower()
        blocked_system_prefixes = (
            "c:\\windows", "c:\\program files", "c:\\program files (x86)",
            "/etc", "/var", "/usr", "/bin", "/sbin", "/root", "/proc", "/sys"
        )
        if any(resolved_lower.startswith(prefix) for prefix in blocked_system_prefixes) or local_dir.parent == local_dir:
            raise ForbiddenException(
                f"Access to sensitive system path '{clean_path_str}' is denied.",
                details=[ErrorDetail(field="source_repository", issue="System paths are forbidden")],
            )"""

new_part = """        path_normalized = clean_path_str.lower().replace("\\\\", "/")
        resolved_normalized = str(local_dir).lower().replace("\\\\", "/")
        blocked_system_prefixes = (
            "c:/windows", "c:/program files", "c:/program files (x86)",
            "/etc", "/var", "/usr", "/bin", "/sbin", "/root", "/proc", "/sys",
            "c:/etc", "c:/var", "c:/usr", "c:/bin", "c:/root"
        )
        if (
            any(path_normalized.startswith(prefix) for prefix in blocked_system_prefixes)
            or any(resolved_normalized.startswith(prefix) for prefix in blocked_system_prefixes)
            or local_dir.parent == local_dir
        ):
            raise ForbiddenException(
                f"Access to sensitive system path '{clean_path_str}' is denied.",
                details=[ErrorDetail(field="source_repository", issue="System paths are forbidden")],
            )"""

if old_part in text:
    text = text.replace(old_part, new_part)
elif old_part.replace("\n", "\r\n") in text:
    text = text.replace(old_part.replace("\n", "\r\n"), new_part.replace("\n", "\r\n"))
else:
    print("Could not match old_part")

p.write_text(text, encoding="utf-8")
print("Done patching jobs.py")

