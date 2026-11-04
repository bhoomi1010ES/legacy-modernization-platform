import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.security import verify_password

async def main():
    engine = create_async_engine('postgresql+asyncpg://postgres:postres123@localhost:5432/rebase_test_w01')
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT user_id, email, role, password_hash FROM users WHERE email = 'alex.morgan@acme.corp'"))
        row = res.first()
        print('Found alex.morgan:', row)
        if row:
            print("Verifies SecurePassword123!:", verify_password("SecurePassword123!", row.password_hash))
            print("Verifies Password123!:", verify_password("Password123!", row.password_hash))
            print("Verifies AdminSecure123!:", verify_password("AdminSecure123!", row.password_hash))

asyncio.run(main())
