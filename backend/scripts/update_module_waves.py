import asyncio
import sys
import uuid
from pathlib import Path
from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.module import Module
from app.models.phase4 import ConversionPlanModel, ConversionPlanModuleModel

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    async with AsyncSessionLocal() as db:
        modules = (await db.execute(select(Module).where(Module.job_id == job_id))).scalars().all()
        for m in modules:
            if not m.dependency_module_ids:
                m.wave_number = 1
            else:
                m.wave_number = 2
        await db.commit()
        
        # Verify
        mods = (await db.execute(select(Module).where(Module.job_id == job_id).order_by(Module.wave_number.asc()))).scalars().all()
        print("Updated modules:")
        for m in mods:
            print(f"  {m.name}: wave={m.wave_number}, status={m.status}, deps={m.dependency_module_ids}")

if __name__ == "__main__":
    asyncio.run(main())

