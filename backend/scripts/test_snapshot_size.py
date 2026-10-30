import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.phase6_workspace import file_snapshot

async def main():
    repo_path = Path("repo_workspaces/job_eb2bbaa9-90ee-4e9d-b340-5e025594126c").resolve()
    try:
        files = await file_snapshot(repo_path)
        print(f"file_snapshot SUCCESS: {len(files)} tracked files.")
        total_size = sum(len(c.encode("utf-8")) for c in files.values())
        print(f"Total size: {total_size} bytes ({total_size / 1024:.1f} KB)")
    except Exception as e:
        print(f"file_snapshot FAILED: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())

