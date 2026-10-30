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
            if a.artifact_type in ("TargetBlueprint", "LegacyModel", "TARGET_BLUEPRINT", "LEGACY_MODEL"):
                content = await svc.storage.get_object(a.storage_path)
                data = json.loads(content.decode("utf-8"))
                print(f"=== {a.artifact_type} v{a.version} ===")
                if a.artifact_type in ("TargetBlueprint", "TARGET_BLUEPRINT"):
                    components = data.get("components", [])
                    print(f"Components ({len(components)}):")
                    for c in components:
                        print(f"  Component: {c.get('component_id')} | name: {c.get('name')} | target: {c.get('target_scope')} | source: {c.get('source_scope')} | deps: {c.get('dependencies')}")
                elif a.artifact_type in ("LegacyModel", "LEGACY_MODEL"):
                    modules = data.get("modules", [])
                    print(f"Legacy Modules ({len(modules)}):")
                    for m in modules:
                        print(f"  Module: {m.get('module_id')} | name: {m.get('name')} | path: {m.get('path')} | deps: {m.get('dependencies')}")

if __name__ == "__main__":
    asyncio.run(main())

