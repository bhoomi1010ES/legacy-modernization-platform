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
        suite = await db.scalar(
            select(Artifact).where(Artifact.job_id == job_id, Artifact.artifact_type == "CHARACTERIZATION_SUITE").order_by(Artifact.version.desc()).limit(1)
        )
        content = await svc.storage.get_object(suite.storage_path)
        data = json.loads(content.decode("utf-8"))
        for c in data.get("cases", []):
            if c.get("module") == "utils":
                print(json.dumps(c, indent=2))
                break

if __name__ == "__main__":
    asyncio.run(main())

