import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.test_case import TestCase
from sqlalchemy import select

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    async with AsyncSessionLocal() as db:
        cases = (await db.execute(select(TestCase).where(TestCase.job_id == job_id))).scalars().all()
        print("Total test cases for job:", len(cases))
        names = {c.name for c in cases}
        print("Unique test case names:", len(names))
        layers = {}
        for c in cases:
            layers[c.test_layer] = layers.get(c.test_layer, 0) + 1
        print("Layers:", layers)

if __name__ == "__main__":
    asyncio.run(main())

