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
from app.models.agent import AgentRun
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
                job_id = existing.job_id
                print(f"  [=] Job '{data['name']}' already exists.")
            else:
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

            # Ensure demo artifacts exist
            art_stmt = select(Artifact).where(Artifact.job_id == job_id)
            art_res = await session.execute(art_stmt)
            if not art_res.scalar_one_or_none():
                art = Artifact(
                    job_id=job_id,
                    artifact_type="ARCHITECTURE_SPEC",
                    version=1,
                    content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    storage_path=f"artifacts/{job_id}/arch_spec_v1.json",
                    content_size_bytes=1024,
                    producing_agent="ArchitectAgent",
                    derived_from=[],
                )
                session.add(art)
                print(f"  [+] Seeded Artifact for {data['name']}")

            # Ensure demo agent run exists
            agent_stmt = select(AgentRun).where(AgentRun.job_id == job_id)
            agent_res = await session.execute(agent_stmt)
            if not agent_res.scalar_one_or_none():
                agent = AgentRun(
                    job_id=job_id,
                    agent_name="ArchitectAgent",
                    model_identifier="claude-3-5-sonnet-20241022",
                    status="COMPLETED",
                    input_tokens=1500,
                    output_tokens=420,
                    cost_usd=Decimal("0.0210"),
                )
                session.add(agent)
                print(f"  [+] Seeded AgentRun for {data['name']}")

        await session.commit()
        print("[SUCCESS] Demo jobs verified and seeded.")


if __name__ == "__main__":
    asyncio.run(seed_demo_jobs())
