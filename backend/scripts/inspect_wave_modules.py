import asyncio
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.module import Module
from app.models.phase4 import ConversionPlanModel, ConversionPlanModuleModel

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    async with AsyncSessionLocal() as db:
        modules = (await db.execute(select(Module).where(Module.job_id == job_id))).scalars().all()
        print(f"Total modules in DB: {len(modules)}")
        for m in modules:
            print(f"  Module: {m.name} | wave: {m.wave_number} | status: {m.status} | target_path: {m.target_path} | legacy_path: {m.legacy_path} | deps: {m.dependency_module_ids}")

        plan = await db.scalar(select(ConversionPlanModel).where(ConversionPlanModel.job_id == job_id).order_by(ConversionPlanModel.version.desc()).limit(1))
        plan_mods = (await db.execute(select(ConversionPlanModuleModel).where(ConversionPlanModuleModel.plan_id == plan.plan_id))).scalars().all()
        print(f"\nPlan modules in DB: {len(plan_mods)}")
        for pm in plan_mods:
            print(f"  PlanModule: {pm.module_id} | name: {pm.name} | target_scope: {pm.target_scope} | source_scope: {pm.source_scope} | deps: {pm.dependencies}")

if __name__ == "__main__":
    asyncio.run(main())

