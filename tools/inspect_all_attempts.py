import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.module import Module, ModuleAttempt
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        m = await db.scalar(select(Module).where(Module.name == 'comp_app-exceptions_c809b4'))
        attempts = (await db.scalars(select(ModuleAttempt).where(ModuleAttempt.module_id == m.module_id).order_by(ModuleAttempt.attempt_number.asc()))).all()
        for att in attempts:
            print(f"Attempt #{att.attempt_number} (status={att.status}): {att.failure_reason}")

if __name__ == "__main__":
    asyncio.run(main())

