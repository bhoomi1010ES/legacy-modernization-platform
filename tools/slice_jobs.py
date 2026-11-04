from pathlib import Path

p = Path('backend/app/api/v1/jobs.py')
lines = p.read_text(encoding='utf-8').splitlines()

new_replacement = [
    '        path_normalized = clean_path_str.lower().replace("\\\\", "/")',
    '        resolved_normalized = str(local_dir).lower().replace("\\\\", "/")',
    '        blocked_system_prefixes = (',
    '            "c:/windows", "c:/program files", "c:/program files (x86)",',
    '            "/etc", "/var", "/usr", "/bin", "/sbin", "/root", "/proc", "/sys",',
    '            "c:/etc", "c:/var", "c:/usr", "c:/bin", "c:/root"',
    '        )',
    '        if (',
    '            any(path_normalized.startswith(prefix) for prefix in blocked_system_prefixes)',
    '            or any(resolved_normalized.startswith(prefix) for prefix in blocked_system_prefixes)',
    '            or local_dir.parent == local_dir',
    '        ):',
    '            raise ForbiddenException(',
    '                f"Access to sensitive system path \'{clean_path_str}\' is denied.",',
    '                details=[ErrorDetail(field="source_repository", issue="System paths are forbidden")],',
    '            )',
]

lines[174:184] = new_replacement
p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print("Successfully replaced lines 174-184 in jobs.py")

