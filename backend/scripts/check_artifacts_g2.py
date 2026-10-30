import asyncio
import json
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.artifact import Artifact
from app.models.workflow import WorkflowGate
from app.services.artifact_service import ArtifactService
from app.services.phase5_engine import canonical, digest

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    svc = ArtifactService()
    async with AsyncSessionLocal() as db:
        suite_art = await db.scalar(
            select(Artifact).where(
                Artifact.job_id == job_id, Artifact.artifact_type == "CHARACTERIZATION_SUITE"
            ).order_by(Artifact.version.desc()).limit(1)
        )
        schema_art = await db.scalar(
            select(Artifact).where(
                Artifact.job_id == job_id, Artifact.artifact_type == "SCHEMA_MIGRATION_PLAN"
            ).order_by(Artifact.version.desc()).limit(1)
        )
        print(f"Current Suite: v{suite_art.version} hash={suite_art.content_hash[:16]}")
        print(f"Current Schema: v{schema_art.version} hash={schema_art.content_hash[:16]}")

if __name__ == "__main__":
    asyncio.run(main())

