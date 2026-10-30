import asyncio
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.phase6_workspace import git
from app.services.secret_redactor import get_secret_redactor

async def main():
    repo_path = Path("repo_workspaces/job_eb2bbaa9-90ee-4e9d-b340-5e025594126c").resolve()
    redactor = get_secret_redactor()
    tracked = (await git(repo_path, "ls-files", "-z")).split("\x00")
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
        redacted = redactor.redact_text(data)
        if redacted != data:
            print(f"SECRET DETECTED IN: {name}")

if __name__ == "__main__":
    asyncio.run(main())

