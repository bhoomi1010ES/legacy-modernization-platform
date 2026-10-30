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
        for name in ['comp_app-exceptions_c809b4', 'comp_app-core_5ca8c3', 'comp_app-dependencies_b6e453']:
            m = await db.scalar(select(Module).where(Module.name == name))
            if not m:
                continue
            attempts = (await db.scalars(select(ModuleAttempt).where(ModuleAttempt.module_id == m.module_id).order_by(ModuleAttempt.attempt_number.desc()))).all()
            for att in attempts[:2]:
                print(f"=== {name} (Attempt #{att.attempt_number}) ===")
                print(f"status: {att.status}")
                print(f"branch: {att.git_branch}")
                print(f"failure_reason: {att.failure_reason}\n")

if __name__ == "__main__":
    asyncio.run(main())

