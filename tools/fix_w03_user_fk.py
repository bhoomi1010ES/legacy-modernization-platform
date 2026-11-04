from pathlib import Path

test_file = Path("backend/tests/test_w03_schema_and_reconciliation.py")
content = test_file.read_text(encoding="utf-8")

old_code = '''    # 1. Seed contradictory test records in an isolated transaction
    test_job = Job(
        job_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        name="W03 Reconciliation Test Job",
        source_repository="https://github.com/example/reconcile-test.git",
        source_revision="main",
        source_stack="python",
        target_stack="django",
        status="FAILED",  # Terminal status
        workflow_phase="FAILED",
        budget_limit_usd=100.0,
        budget_used_usd=10.0,
        max_repair_attempts=3,
        owner_user_id=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )
    db_session.add(test_job)'''

new_code = '''    from app.models.user import User

    test_user = User(
        user_id=uuid.uuid4(),
        email=f"w03_test_user_{uuid.uuid4().hex[:6]}@example.com",
        full_name="W03 Test User",
        password_hash="mock_hash_xyz",
        role="DEVELOPER",
        status="ACTIVE",
    )
    db_session.add(test_user)
    await db_session.flush()

    # 1. Seed contradictory test records in an isolated transaction
    test_job = Job(
        job_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        name="W03 Reconciliation Test Job",
        source_repository="https://github.com/example/reconcile-test.git",
        source_revision="main",
        source_stack="python",
        target_stack="django",
        status="FAILED",  # Terminal status
        workflow_phase="FAILED",
        budget_limit_usd=100.0,
        budget_used_usd=10.0,
        max_repair_attempts=3,
        owner_user_id=test_user.user_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(test_job)'''

content = content.replace(old_code, new_code, 1)
test_file.write_text(content, encoding="utf-8")
print("Updated test_job owner_user_id in test_w03_schema_and_reconciliation.py")

