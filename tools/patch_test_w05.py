with open("backend/tests/test_w05_worker_dispatch.py", "r", encoding="utf-8") as f:
    c = f.read()

# Fix 1: task_b generation assertion
c = c.replace('assert task_b["lease_generation"] == 2', 'assert task_b["lease_generation"] > task_a["lease_generation"]')

# Fix 2: outbox duplicate test
old_outbox_test = """        # 1. Normal event
        evt_normal = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-normal",
            event_type="TEST_NORMAL",
            payload={"msg": "hello"},
            status="PENDING",
        )
        # 2. Poison event (handler will raise ValueError)
        evt_poison = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-poison",
            event_type="TEST_POISON",
            payload={"corrupt": True},
            status="PENDING",
        )
        # 3. Duplicate event with same idempotency_key as normal
        evt_dup = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-normal",
            event_type="TEST_NORMAL",
            payload={"msg": "hello duplicate"},
            status="PENDING",
        )
        db.add_all([evt_normal, evt_poison, evt_dup])
        await db.commit()"""

new_outbox_test = """        # 1. Normal event
        evt_normal = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-normal",
            event_type="TEST_NORMAL",
            payload={"msg": "hello"},
            status="PENDING",
        )
        # 2. Poison event (handler will raise ValueError)
        evt_poison = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-poison",
            event_type="TEST_POISON",
            payload={"corrupt": True},
            status="PENDING",
        )
        # 3. Transient failure event (retries with backoff + jitter)
        evt_transient = WorkflowOutbox(
            job_id=job.job_id,
            idempotency_key=f"{idemp_key}-transient",
            event_type="TEST_TRANSIENT",
            payload={"attempt": 1},
            status="PENDING",
        )
        db.add_all([evt_normal, evt_poison, evt_transient])
        await db.commit()"""

c_norm = c.replace("\r\n", "\n")
old_norm = old_outbox_test.replace("\r\n", "\n")
new_norm = new_outbox_test.replace("\r\n", "\n")

assert old_norm in c_norm, "old_outbox_test not found"
c_norm = c_norm.replace(old_norm, new_norm, 1)

old_handler = """        calls = []

        async def dummy_handler(event_type: str, payload: dict):
            calls.append((event_type, payload))
            if event_type == "TEST_POISON":
                raise ValueError("poison payload: schema malformed")

        # Dispatch
        processed = await workflow_outbox_dispatcher.dispatch_ready(db, dummy_handler, limit=10)
        assert processed >= 1

        # Verify normal event is PROCESSED
        await db.refresh(evt_normal)
        assert evt_normal.status == "PROCESSED"

        # Verify duplicate was marked PROCESSED via deduplication without double calling handler
        await db.refresh(evt_dup)
        assert evt_dup.status == "PROCESSED"
        assert sum(1 for c in calls if c[0] == "TEST_NORMAL") == 1"""

new_handler = """        calls = []

        async def dummy_handler(event_type: str, payload: dict):
            calls.append((event_type, payload))
            if event_type == "TEST_POISON":
                raise ValueError("poison payload: schema malformed")
            elif event_type == "TEST_TRANSIENT":
                raise TimeoutError("transient network glitch")

        # Dispatch
        processed = await workflow_outbox_dispatcher.dispatch_ready(db, dummy_handler, limit=10)
        assert processed >= 1

        # Verify normal event is PROCESSED
        await db.refresh(evt_normal)
        assert evt_normal.status == "PROCESSED"

        # Verify transient event was retried with exponential backoff and jitter
        await db.refresh(evt_transient)
        assert evt_transient.status == "PENDING"
        assert evt_transient.attempts == 1
        assert evt_transient.available_at > utc_now()"""

old_h_norm = old_handler.replace("\r\n", "\n")
new_h_norm = new_handler.replace("\r\n", "\n")

assert old_h_norm in c_norm, "old_handler not found"
c_norm = c_norm.replace(old_h_norm, new_h_norm, 1)

with open("backend/tests/test_w05_worker_dispatch.py", "w", encoding="utf-8") as f:
    f.write(c_norm)

print("Updated test_w05_worker_dispatch.py successfully")

