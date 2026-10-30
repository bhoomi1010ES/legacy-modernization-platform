import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(text("SELECT sequence, checkpoint_kind, node_name, state_payload FROM workflow_checkpoints WHERE job_id = 'eb2bbaa9-90ee-4e9d-b340-5e025594126c' ORDER BY sequence DESC LIMIT 10"))
        for r in res.fetchall():
            state = r[3] or {}
            print(f"Seq {r[0]}: kind={r[1]}, node={r[2]}, status={state.get('status')}, active_node={state.get('active_node')}")

if __name__ == '__main__':
    asyncio.run(check())

