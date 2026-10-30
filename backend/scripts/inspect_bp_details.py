import asyncio
import json
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.artifact import Artifact
from app.services.artifact_service import ArtifactService

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    svc = ArtifactService()
    async with AsyncSessionLocal() as db:
        artifacts = (await db.execute(select(Artifact).where(Artifact.job_id == job_id))).scalars().all()
        for a in artifacts:
            if a.artifact_type in ("TargetBlueprint", "TARGET_BLUEPRINT"):
                content = await svc.storage.get_object(a.storage_path)
                data = json.loads(content.decode("utf-8"))
                print(f"TargetBlueprint v{a.version} (id={a.artifact_id}): {len(data.get('components', []))} components")
                for c in data.get("components", []):
                    print(f"  Component: {c.get('component_id')} | name: {c.get('name')} | deps: {c.get('dependencies')}")
                break
        from app.models.phase4 import LegacyModelRecord
        leg = (await db.execute(select(LegacyModelRecord).where(LegacyModelRecord.job_id == job_id))).scalars().first()
        if leg:
            print("\nLegacyModelRecord dependencies_payload:", leg.dependencies_payload)

if __name__ == "__main__":
    asyncio.run(main())

