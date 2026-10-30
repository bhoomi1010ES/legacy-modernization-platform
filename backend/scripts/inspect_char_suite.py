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
        cases = data.get("cases", [])
        print(f"Total cases: {len(cases)}")
        outcomes = {}
        for c in cases:
            o = c.get("outcome")
            outcomes[o] = outcomes.get(o, 0) + 1
        print("Outcomes:", outcomes)
        
        non_passed = [c for c in cases if c.get("outcome") != "PASSED"]
        print(f"Non-passed cases: {len(non_passed)}")
        for c in non_passed[:10]:
            print(f"  Case: {c.get('name')} | outcome: {c.get('outcome')} | id: {c.get('test_case_id')}")

if __name__ == "__main__":
    asyncio.run(main())

