path = r"backend/tests/test_w04_supervisor_authority.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Store owner_id before commit
target1 = '''            job = await _create_test_job(db, JobStatus.CREATED)
            owner, _ = await _get_test_users(db)

            # 1. StartJob
            start_cmd = StartJobCommand(job_id=job.job_id, actor_id=str(owner.user_id))'''

rep1 = '''            job = await _create_test_job(db, JobStatus.CREATED)
            owner, _ = await _get_test_users(db)
            owner_id = str(owner.user_id)

            # 1. StartJob
            start_cmd = StartJobCommand(job_id=job.job_id, actor_id=owner_id)'''

c = c.replace(target1, rep1, 1)
c = c.replace("actor_id=str(owner.user_id), reason=\"Scheduled freeze\"", "actor_id=owner_id, reason=\"Scheduled freeze\"")
c = c.replace("actor_id=str(owner.user_id))", "actor_id=owner_id)")
c = c.replace("actor_id=str(owner.user_id), reason=\"Operator abort\"", "actor_id=owner_id, reason=\"Operator abort\"")

# 2. Fix environment monkeypatch
target2 = '    monkeypatch.setattr(settings, "APP_ENV", "production")'
rep2 = '    monkeypatch.setattr(settings, "ENVIRONMENT", "production")'
c = c.replace(target2, rep2, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated test_w04_supervisor_authority.py successfully")

