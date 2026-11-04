path = r"backend/tests/test_w04_supervisor_authority.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace("async def _create_test_job(db, status: JobStatus = JobStatus.CREATED) -> Job:\n    owner, _ = await _get_test_users(db)\n        owner_id = str(owner.user_id)\n", "async def _create_test_job(db, status: JobStatus = JobStatus.CREATED) -> Job:\n    owner, _ = await _get_test_users(db)\n")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Removed line 72")

