
import asyncio
import json
from uuid import UUID
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.phase4 import TargetBlueprintModel, LegacyModelRecord

async def check():
    async with AsyncSessionLocal() as db:
        jid = UUID('eb2bbaa9-90ee-4e9d-b340-5e025594126c')
        bp = (await db.execute(select(TargetBlueprintModel).where(TargetBlueprintModel.job_id == jid).order_by(TargetBlueprintModel.version.desc()))).scalars().first()
        print('=== TargetBlueprint components ===')
        for c in bp.components_payload:
            print(f"  Component: {c.get('name')} id={c.get('component_id')} path={c.get('target_path')} legacy={c.get('source_path')} deps={c.get('dependencies')}")
        leg = (await db.execute(select(LegacyModelRecord).where(LegacyModelRecord.job_id == jid).order_by(LegacyModelRecord.version.desc()))).scalars().first()
        print('=== LegacyModel modules ===')
        for m in leg.modules_payload:
            print(f"  Module: {m.get('name')} path={m.get('path')} deps={m.get('dependencies')}")

if __name__ == '__main__':
    asyncio.run(check())
