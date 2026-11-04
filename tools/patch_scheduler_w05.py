import re

with open("backend/app/services/dependency_scheduler.py", "r", encoding="utf-8") as f:
    c = f.read()

# Add uuid import if missing
if "import uuid" not in c:
    c = "import uuid\n" + c

# Add WorkflowOutbox import if missing
if "WorkflowOutbox" not in c:
    c = c.replace("from app.models.workflow import WorkflowGate", "from app.models.workflow import WorkflowGate, WorkflowOutbox")

old_block = """            module.status = "LEASED"
            module.lease_owner = worker_id
            module.lease_expires_at = now + timedelta(seconds=lease_seconds)
            module.lease_heartbeat_at = now
            module.lease_generation += 1
            claimed.append(module)"""

new_block = """            module.status = "LEASED"
            module.lease_owner = worker_id
            module.lease_expires_at = now + timedelta(seconds=lease_seconds)
            module.lease_heartbeat_at = now
            module.lease_generation += 1
            module.lease_token = str(uuid.uuid4())
            db.add(WorkflowOutbox(
                job_id=job.job_id,
                idempotency_key=f"task-leased-{module.module_id}-{module.lease_generation}",
                event_type="TASK_LEASED",
                payload={
                    "job_id": str(job.job_id),
                    "module_id": str(module.module_id),
                    "module_name": module.name,
                    "worker_id": worker_id,
                    "lease_generation": module.lease_generation,
                    "lease_token": module.lease_token,
                    "lease_expires_at": module.lease_expires_at.isoformat(),
                },
                status="PENDING",
            ))
            claimed.append(module)"""

c_norm = c.replace("\r\n", "\n")
old_norm = old_block.replace("\r\n", "\n")
new_norm = new_block.replace("\r\n", "\n")

assert old_norm in c_norm, "old_block not found in dependency_scheduler.py"
c_norm = c_norm.replace(old_norm, new_norm, 1)

with open("backend/app/services/dependency_scheduler.py", "w", encoding="utf-8") as f:
    f.write(c_norm)

print("Updated dependency_scheduler.py successfully")

