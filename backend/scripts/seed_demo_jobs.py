"""Seed baseline demo jobs and memberships for development and testing."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
import uuid

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.artifact import Artifact
from app.models.audit import AuditEvent
from app.models.job import Job, JobMembership
from app.models.user import User

DEMO_JOBS = [
    {
        "name": "JOB-0248",
        "description": "Commerce API",
        "source_repository": "https://github.com/acme/commerce-api",
        "source_revision": "main",
        "source_stack": "Java 11 / Spring Boot",
        "target_stack": "TypeScript / Node.js 22 / NestJS",
        "status": "CONVERTING",
        "budget_limit_usd": Decimal("150.00"),
        "budget_used_usd": Decimal("42.80"),
        "max_repair_attempts": 3,
        "integration_branch": "job/JOB-0248/integration",
    },
    {
        "name": "JOB-0247",
        "description": "Customer Portal",
        "source_repository": "https://github.com/acme/customer-portal",
        "source_revision": "v2.1",
        "source_stack": "Java 8 / Spring MVC",
        "target_stack": "TypeScript / Node.js 22 / NestJS",
        "status": "AWAITING_GATE_G1",
        "budget_limit_usd": Decimal("100.00"),
        "budget_used_usd": Decimal("18.35"),
        "max_repair_attempts": 3,
    },
    {
        "name": "JOB-0245",
        "description": "Inventory System",
        "source_repository": "https://github.com/acme/inventory-system",
        "source_revision": "main",
        "source_stack": "Java 17 / Spring Boot",
        "target_stack": "TypeScript / Node.js 22 / NestJS",
        "status": "COMPLETED",
        "budget_limit_usd": Decimal("150.00"),
        "budget_used_usd": Decimal("87.45"),
        "max_repair_attempts": 3,
        "integration_branch": "job/JOB-0245/integration",
        "target_repository": "https://github.com/acme/inventory-system/pull/142",
    },
]


async def seed_demo_jobs():
    async with AsyncSessionLocal() as session:
        # Find admin user
        user_stmt = select(User).where(User.email == "alex.morgan@acme.corp")
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            print("[ERROR] User alex.morgan@acme.corp not found. Run create_admin.py first.")
            return

        for data in DEMO_JOBS:
            stmt = select(Job).where(Job.name == data["name"])
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            if existing:
                print(f"  [=] Job '{data['name']}' already exists.")
                continue

            job_id = uuid.uuid4()
            job = Job(
                job_id=job_id,
                name=data["name"],
                description=data["description"],
                source_repository=data["source_repository"],
                source_revision=data["source_revision"],
                source_stack=data["source_stack"],
                target_stack=data["target_stack"],
                status=data["status"],
                budget_limit_usd=data["budget_limit_usd"],
                budget_used_usd=data["budget_used_usd"],
                max_repair_attempts=data["max_repair_attempts"],
                integration_branch=data.get("integration_branch"),
                target_repository=data.get("target_repository"),
                owner_user_id=user.user_id,
            )
            session.add(job)

            # Owner membership
            mem = JobMembership(
                job_id=job_id,
                user_id=user.user_id,
                role_id="ADMIN",
            )
            session.add(mem)

            # Initial audit event
            audit = AuditEvent(
                job_id=job_id,
                event_type="JOB_CREATED",
                actor_type="USER",
                actor_id=str(user.user_id),
                target_resource=str(job_id),
                payload={"name": job.name, "source": job.source_repository},
            )
            session.add(audit)
            print(f"  [+] Seeded Job: {data['name']} ({data['description']})")

        await session.commit()
        print("[SUCCESS] Demo jobs verified and seeded.")


if __name__ == "__main__":
    asyncio.run(seed_demo_jobs())
