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
        suite = (await db.execute(
            select(Artifact).where(Artifact.job_id == job_id, Artifact.artifact_type == "CHARACTERIZATION_SUITE").order_by(Artifact.version.desc())
        )).scalars().first()
        content = await svc.storage.get_object(suite.storage_path)
        data = json.loads(content.decode("utf-8"))
        print("g2_readiness:", json.dumps(data.get("g2_readiness"), indent=2))
        print("schema_hash:", data.get("schema_hash"))
        print("schema_artifact_id:", data.get("schema_artifact_id"))

if __name__ == "__main__":
    asyncio.run(main())

