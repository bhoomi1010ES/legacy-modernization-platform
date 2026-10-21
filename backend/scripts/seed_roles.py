"""Seed standard RBAC roles and permissions into database."""

import asyncio
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.role import Role
from app.domain.state_machine import RBACPolicy

ROLES_METADATA = [
    {
        "role_id": "SUPER_ADMIN",
        "name": "Super Administrator",
        "description": "Workspace Owner with Full System Control and User Provisioning.",
        "permissions": sorted(list(RBACPolicy.ROLE_PERMISSIONS["SUPER_ADMIN"])),
    },
    {
        "role_id": "ADMIN",
        "name": "Workspace Administrator",
        "description": "Job Creator, Workspace Settings, and Approval Governance.",
        "permissions": sorted(list(RBACPolicy.ROLE_PERMISSIONS["ADMIN"])),
    },
    {
        "role_id": "REVIEWER",
        "name": "Gate Reviewer",
        "description": "Authorized Human Approver for G1-G4 checkpoints and waiver signoff.",
        "permissions": sorted(list(RBACPolicy.ROLE_PERMISSIONS["REVIEWER"])),
    },
    {
        "role_id": "DEVELOPER",
        "name": "Platform Developer",
        "description": "Job Explorer, Artifact Inspector, and Code Verification Analyst.",
        "permissions": sorted(list(RBACPolicy.ROLE_PERMISSIONS["DEVELOPER"])),
    },
    {
        "role_id": "VIEWER",
        "name": "Read-Only Viewer",
        "description": "Read-Only inspection of modernization progress and public reports.",
        "permissions": sorted(list(RBACPolicy.ROLE_PERMISSIONS["VIEWER"])),
    },
]


async def seed_roles():
    async with AsyncSessionLocal() as session:
        for r_meta in ROLES_METADATA:
            stmt = select(Role).where(Role.role_id == r_meta["role_id"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                new_role = Role(
                    role_id=r_meta["role_id"],
                    name=r_meta["name"],
                    description=r_meta["description"],
                    permissions=r_meta["permissions"],
                )
                session.add(new_role)
                print(f"  [+] Created Role: {r_meta['role_id']} ({r_meta['name']})")
            else:
                existing.permissions = r_meta["permissions"]
                existing.description = r_meta["description"]
                existing.name = r_meta["name"]
                print(f"  [=] Synchronized Role: {r_meta['role_id']}")

        await session.commit()
        print("[SUCCESS] All 5 standard RBAC roles verified and seeded.")


if __name__ == "__main__":
    asyncio.run(seed_roles())
