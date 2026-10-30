import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.user import User

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        owner = await db.get(User, job.owner_user_id) if job.owner_user_id else None
        print(f"Job: {job.job_id} | Owner: {job.owner_user_id} | Owner role: {owner.role if owner else None}")

if __name__ == "__main__":
    asyncio.run(main())

