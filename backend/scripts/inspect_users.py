import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        for u in users:
            print(f"User: {u.user_id} | email: {u.email} | role: {u.role} | status: {u.status}")

if __name__ == "__main__":
    asyncio.run(main())
