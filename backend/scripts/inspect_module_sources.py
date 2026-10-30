import asyncio
import json
import sys
import uuid
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.module import Module
from app.services.repository_workspace_service import repository_workspace_service
from app.services.phase6_workspace import file_snapshot
from sqlalchemy import select

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    repo_path = repository_workspace_service.get_workspace_path(job_id)
    print("Repo path from service:", repo_path)
    print("Exists:", repo_path.exists())
    if not repo_path.exists():
        async with AsyncSessionLocal() as db:
            from app.models.job import Job
            job = await db.get(Job, job_id)
            print("Ensuring workspace via repository_workspace_service...")
            repo_path = await repository_workspace_service.ensure_workspace(db, job)
            print("Ensured workspace:", repo_path)
    sources = await file_snapshot(repo_path)
    print(f"Total files in Spendwise workspace: {len(sources)}")
    
    async with AsyncSessionLocal() as db:
        mods = (await db.execute(select(Module).where(Module.job_id == job_id))).scalars().all()
    async with AsyncSessionLocal() as db:
        mods = (await db.execute(select(Module).where(Module.job_id == job_id))).scalars().all()
        for m in mods:
            scopes = [PurePosixPath(m.legacy_path)]
            other_scopes = [PurePosixPath(o.legacy_path) for o in mods if o.module_id != m.module_id and o.legacy_path]
            filtered = {}
            for p, v in sources.items():
                posix_p = PurePosixPath(p)
                if posix_p.name in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"):
                    continue
                if not any(posix_p == s or s in posix_p.parents for s in scopes):
                    continue
                if any(other in posix_p.parents and not any(other in s.parents for s in scopes) for other in other_scopes):
                    continue
                filtered[p] = v
            size = len(json.dumps(filtered).encode())
            print(f"Module {m.name:32} | files: {len(filtered):2} | size: {size:7} bytes | <= 256KB: {size <= 262144}")

if __name__ == "__main__":
    asyncio.run(main())
