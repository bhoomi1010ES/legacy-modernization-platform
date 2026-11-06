import asyncio
import uuid
import json
from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.user import User
from app.services.supervisor_service import supervisor_service
from app.services.phase6_service import execute_attempt, newest
from sqlalchemy import select

async def main():
    job_id = uuid.UUID("26b905d7-0013-4dd2-84ec-39d8809d280b")
    module_id = uuid.UUID("3037b367-9909-5002-b5e7-d48c8f50c9af")
    
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        module = await db.get(Module, module_id)
        user = await db.scalar(select(User).where(User.email == "bhoomi.edgesphere@gmail.com"))
        last = await newest(db, module.module_id)
        
        print(f"Queueing conversion for {module.name} with previous attempt {last.attempt_number if last else None}...")
        attempt = await supervisor_service.queue_module_conversion(
            db, job, module, f"remediation-repair-{uuid.uuid4().hex[:8]}", str(user.user_id),
            previous=last, rationale="Remediated typing annotations, test-less DDL NOT_APPLICABLE handling, and target adapter execution"
        )
        print(f"Queued Attempt {attempt.attempt_number} (ID: {attempt.attempt_id}), status: {attempt.status}")
        
    print(f"\nExecuting Attempt {attempt.attempt_id}...")
    async with AsyncSessionLocal() as db:
        await execute_attempt(db, attempt.attempt_id)
        
    async with AsyncSessionLocal() as db:
        att = await db.get(ModuleAttempt, attempt.attempt_id)
        mod = await db.get(Module, module_id)
        print(f"\n==========================================")
        print(f"Finished Attempt {att.attempt_number} (ID: {att.attempt_id})")
        print(f"Attempt Status: {att.status}")
        print(f"Failure Reason: {att.failure_reason}")
        print(f"Module Status: {mod.status}")
        print(f"==========================================")

if __name__ == "__main__":
    asyncio.run(main())
