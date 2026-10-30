import asyncio
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.phase6_workspace import git
from app.services.secret_redactor import get_secret_redactor, SECRET_PATTERNS

async def main():
    repo_path = Path("repo_workspaces/job_eb2bbaa9-90ee-4e9d-b340-5e025594126c").resolve()
    redactor = get_secret_redactor()
    tracked = (await git(repo_path, "ls-files", "-z")).split("\x00")
    print(f"Custom sensitive values registered: {len(redactor._custom_values)}")
    for val in redactor._custom_values:
        print(f"  Secret prefix: {val[:8]}...")

    leaked = []
    for name in tracked:
        if not name or any(
            p in {".git", ".env", "node_modules", ".agents", ".codex"}
            or p.startswith(".env.")
            for p in PurePosixPath(name).parts
        ):
            continue
        path = repo_path / name
        if not path.is_file():
            continue
        try:
            data = path.read_text(encoding="utf-8")
        except Exception:
            continue

        # Check custom host environment secrets
        for secret in redactor._custom_values:
            if secret in data:
                leaked.append((name, "CUSTOM_ENV_SECRET"))

        # Check real credential patterns (sk-, ghp-, AWS keys, Private keys)
        for pattern, label in SECRET_PATTERNS[:7]: # API keys, AWS, Private keys
            if pattern.search(data):
                leaked.append((name, label))

    print(f"Real leaked credentials count: {len(leaked)}")
    for name, reason in leaked:
        print(f"  {name}: {reason}")

if __name__ == "__main__":
    asyncio.run(main())

