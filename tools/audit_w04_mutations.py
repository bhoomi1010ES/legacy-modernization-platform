import os
import re

backend_dir = r"c:\Users\lenovo\Desktop\rebase\backend"
skip_dirs = {".venv", "__pycache__", ".test_runs", ".pytest_cache", "node_modules", ".git"}

patterns = {
    "job_status": re.compile(r"(\.status\s*=\s*['\"][A-Z_]+['\"]|status\s*=\s*JobStatus\.[A-Z_]+|job\.status\s*=)"),
    "module_status": re.compile(r"(module\.status\s*=|m\.status\s*=|Module\.status\s*=)"),
    "gate_status": re.compile(r"(gate\.status\s*=|WorkflowGate\.status\s*=)"),
    "attempt_status": re.compile(r"(attempt\.status\s*=|ModuleAttempt\.status\s*=)"),
    "background_tasks": re.compile(r"(asyncio\.create_task|BackgroundTasks|background_tasks\.add_task)"),
    "continuous_pipeline": re.compile(r"(ContinuousPipelineService|continuous_pipeline)")
}

findings = {k: [] for k in patterns}

for root, dirs, files in os.walk(backend_dir):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for f in files:
        if f.endswith(".py"):
            p = os.path.join(root, f)
            rel_path = os.path.relpath(p, backend_dir)
            try:
                with open(p, "r", encoding="utf-8") as fp:
                    for idx, line in enumerate(fp, 1):
                        for k, pat in patterns.items():
                            if pat.search(line):
                                findings[k].append((rel_path, idx, line.strip()))
            except Exception as e:
                pass

print("=== ENUMERATION REPORT ===")
for k, items in findings.items():
    print(f"\n--- {k.upper()} ({len(items)} hits) ---")
    files_seen = {}
    for rel_path, idx, line in items:
        files_seen.setdefault(rel_path, []).append((idx, line))
    for rel_path, occurrences in files_seen.items():
        print(f"  {rel_path}: {len(occurrences)} occurrences")
        for idx, line in occurrences[:3]:
            print(f"    L{idx}: {line[:100]}")
        if len(occurrences) > 3:
            print(f"    ... and {len(occurrences) - 3} more")
