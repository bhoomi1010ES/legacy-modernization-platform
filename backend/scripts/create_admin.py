"""CLI and script for bootstrapping an initial administrator account."""

import argparse
import asyncio
import os
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def create_admin(email: str, password: str, full_name: str, role: str = "SUPER_ADMIN"):
    async with AsyncSessionLocal() as session:
        clean_email = email.strip().lower()
        stmt = select(User).where(User.email == clean_email)
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.full_name = full_name
            existing.role = role
            existing.status = "ACTIVE"
            existing.password_hash = hash_password(password)
            await session.commit()
            print(f"[SUCCESS] Updated existing user '{clean_email}' with role '{role}'.")
            return

        new_user = User(
            email=clean_email,
            full_name=full_name,
            role=role,
            status="ACTIVE",
            password_hash=hash_password(password),
        )
        session.add(new_user)
        await session.commit()
        print(f"[SUCCESS] Created new user '{clean_email}' with role '{role}'.")


def main():
    parser = argparse.ArgumentParser(description="Create or update an administrative user.")
    parser.add_argument("--email", default=os.getenv("INITIAL_ADMIN_EMAIL", "alex.morgan@acme.corp"), help="Admin email")
    parser.add_argument("--password", default=os.getenv("INITIAL_ADMIN_PASSWORD", "AdminSecure123!"), help="Admin password")
    parser.add_argument("--name", default=os.getenv("INITIAL_ADMIN_NAME", "Alex Morgan"), help="Display name")
    parser.add_argument("--role", default="ADMIN", help="Role (SUPER_ADMIN, ADMIN, etc.)")

    args = parser.parse_args()
    asyncio.run(create_admin(args.email, args.password, args.name, args.role))


if __name__ == "__main__":
    main()
