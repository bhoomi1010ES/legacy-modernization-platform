import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.services.supervisor_service import supervisor_service
from app.models.job import Job
from app.models.module import Module

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    module_id = uuid.UUID("8e393447-0a4d-5786-8bf6-c01a077102b7")
    
    async with AsyncSessionLocal() as db:
        job_before = await db.get(Job, job_id)
        mod_before = await db.get(Module, module_id)
        print(f"BEFORE: Job status={job_before.status}, active_node={job_before.active_node}")
        print(f"BEFORE: Module {mod_before.name} status={mod_before.status}, retries={mod_before.retry_count}")
        
        result = await supervisor_service.recover_failed_phase6_job(
            db=db,
            job_id=job_id,
            rationale="Recovered Phase 6 Wave 2 after increasing model token limit to 16k and adding chunked generation fallback.",
            target_module_id=module_id,
            actor_id="AdminLeadArchitect",
        )
        print("RECOVERY RESULT:", result)
        
        job_after = await db.get(Job, job_id)
        mod_after = await db.get(Module, module_id)
        print(f"AFTER: Job status={job_after.status}, active_node={job_after.active_node}, last_transition={job_after.last_transition}")
        print(f"AFTER: Module {mod_after.name} status={mod_after.status}, retries={mod_after.retry_count}")

if __name__ == "__main__":
    asyncio.run(main())

