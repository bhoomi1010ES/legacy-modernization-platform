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
from app.services.phase5_service import validation_status

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    svc = ArtifactService()
    async with AsyncSessionLocal() as db:
        schema = (await db.execute(
            select(Artifact).where(Artifact.job_id == job_id, Artifact.artifact_type == "SCHEMA_MIGRATION_PLAN").order_by(Artifact.version.desc())
        )).scalars().first()
        content = await svc.storage.get_object(schema.storage_path)
        data = json.loads(content.decode("utf-8"))
        print("Schema plan status:", data.get("status"))
        print("Tables count:", len(data.get("tables", [])))
        val_status = await validation_status(db, job_id, schema.content_hash)
        print("Validation status:", val_status)

if __name__ == "__main__":
    asyncio.run(main())

