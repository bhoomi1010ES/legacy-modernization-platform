import asyncio
import json
from app.core.database import AsyncSessionLocal
from app.models.artifact import Artifact
from app.models.module import Module
from app.core.storage import get_storage_adapter
from uuid import UUID

async def main():
    async with AsyncSessionLocal() as db:
        modules = (await db.scalars(select(Module).where(Module.job_id == UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")))).all()
        storage = get_storage_adapter()
        for m in modules:
            if m.status == "VERIFIED":
                arts = (await db.scalars(
                    select(Artifact)
                    .where(Artifact.module_id == m.module_id, Artifact.artifact_type == "CONVERTED_MODULE")
                    .order_by(Artifact.version.desc())
                )).all()
                if arts:
                    latest_art = arts[0]
                    raw = await storage.get_object(latest_art.storage_path)
                    data = json.loads(raw.decode('utf-8')) if isinstance(raw, (bytes, bytearray)) else raw
                    keys = list(data.keys()) if isinstance(data, dict) else []
                    commit = data.get("commit_hash") or data.get("commit") or data.get("git_commit")
                    branch = data.get("branch") or data.get("git_branch")
                    print(f"VERIFIED {m.name:30} | Art {latest_art.artifact_id} | Keys: {keys} | Commit: {commit} | Branch: {branch}")
                else:
                    print(f"VERIFIED {m.name:30} | NO CONVERTED_MODULE ARTIFACT")

if __name__ == '__main__':
    from sqlalchemy import select
    asyncio.run(main())

