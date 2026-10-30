import asyncio, sys, json
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
from app.core.database import AsyncSessionLocal
from sqlalchemy import text
from app.services.phase5_service import read_payload
from app.models.artifact import Artifact

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT artifact_id FROM artifacts WHERE job_id = 'eb2bbaa9-90ee-4e9d-b340-5e025594126c' AND artifact_type = 'VERIFICATION_REPORT' LIMIT 1"))
        row = res.fetchone()
        if row:
            art = await db.get(Artifact, row[0])
            data = await read_payload(art)
            print("Passed:", data.get("passed"))
            print("Checks:", [c.get("category") + ": " + c.get("status") for c in data.get("checks", [])])
            print("Cases count:", len(data.get("cases", [])))

if __name__ == '__main__':
    asyncio.run(check())
