from pathlib import Path
p = Path("backend/tests/test_w08_planner_dag_and_scheduler.py")
text = p.read_text(encoding="utf-8")
old_job = """    job = Job(
        job_id=job_id,
        owner_id=owner_id,
        owner_user_id=owner_id,
        repository_name=f"repo_{name_suffix}",
        source_repository=f"https://github.com/example/repo_{name_suffix}.git",
        status="CONVERTING",
        budget_limit_usd=Decimal("500.00"),
        budget_used_usd=Decimal("0.00"),
        max_parallel_tasks=5,
        provider_concurrency_limit=5,
        sandbox_concurrency_limit=5,
    )"""

new_job = """    job = Job(
        job_id=job_id,
        name=f"job_{name_suffix}",
        owner_user_id=owner_id,
        source_repository=f"https://github.com/example/repo_{name_suffix}.git",
        status="CONVERTING",
        budget_limit_usd=Decimal("500.00"),
        budget_used_usd=Decimal("0.00"),
        max_parallel_tasks=5,
        provider_concurrency_limit=5,
        sandbox_concurrency_limit=5,
    )"""

assert old_job in text, "old_job not found in test_w08_planner_dag_and_scheduler.py"
text = text.replace(old_job, new_job, 1)
p.write_text(text, encoding="utf-8")
print("Successfully fixed Job in test_w08_planner_dag_and_scheduler.py")
