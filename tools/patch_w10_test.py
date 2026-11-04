with open("backend/tests/test_w10_independent_verifier.py", "r", encoding="utf-8") as f:
    c = f.read()

# 1. Fix test_verifier_separate_durable_work_item_and_lease
old_1 = """    db, job, _, storage, module, _ = ready
    attempt = await service.queue_attempt(
        db,
        job=job,
        module=module,
        operation="convert",
        rationale="Initial module conversion attempt",
    )"""

new_1 = """    db, job, _, storage, module, _ = ready
    attempt = await queued(ready)"""

assert old_1 in c, "old_1 not found"
c = c.replace(old_1, new_1, 1)

# 2. Fix test_repair_creates_new_attempt_with_target_failed_tests
old_2 = """    first = await service.queue_attempt(
        db,
        ready[1],
        module,
        operation="convert",
        rationale="Attempt 1: buggy output",
    )"""

new_2 = """    first = await queued(ready)"""

assert old_2 in c, "old_2 not found"
c = c.replace(old_2, new_2, 1)

old_2b = """    # Queue second attempt as repair
    second = await service.queue_attempt(
        db,
        ready[1],
        module,
        operation="repair",
        previous=first,
        rationale="Repair addition regression identified by frozen characterization suite",
    )"""

new_2b = """    # Queue second attempt as repair
    second = await queued(
        ready,
        "repair",
        previous=first,
        rationale="Repair addition regression identified by frozen characterization suite",
    )"""

assert old_2b in c, "old_2b not found"
c = c.replace(old_2b, new_2b, 1)

# 3. Fix test_repeated_failure_exhaustion_escalates_to_waiting_for_human
old_3 = """    first = await service.queue_attempt(db, job, module, operation="convert", rationale="Convert attempt 1")
    await service.execute_attempt(db, first.attempt_id, gateway=gateway)
    assert first.status == "REPAIR_REQUIRED"

    # Queue repair attempt
    second = await service.queue_attempt(
        db,
        job,
        module,
        operation="repair",
        previous=first,
        rationale="Repair attempt 2",
    )
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)

    # Reached limit and same failure -> WAITING_FOR_HUMAN
    assert second.status == "WAITING_FOR_HUMAN"

    # Any further automatic queue attempt must be rejected with ConflictException
    with pytest.raises(ConflictException, match="Repair attempt limit exhausted; human escalation required"):
        await service.queue_attempt(
            db,
            job,
            module,
            operation="repair",
            previous=second,
            rationale="Unapproved third attempt",
        )"""

new_3 = """    first = await queued(ready)
    await service.execute_attempt(db, first.attempt_id, gateway=gateway)
    assert first.status == "REPAIR_REQUIRED"

    # Queue repair attempt
    second = await queued(
        ready,
        "repair",
        previous=first,
        rationale="Repair exact failed frozen characterization case",
    )
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)

    # Reached limit and same failure -> WAITING_FOR_HUMAN
    assert second.status == "WAITING_FOR_HUMAN"

    # Any further automatic queue attempt must be rejected with ConflictException
    with pytest.raises(ConflictException):
        await queued(
            ready,
            "again",
            previous=second,
            rationale="A third automatic repeat must not be scheduled",
        )"""

assert old_3 in c, "old_3 not found"
c = c.replace(old_3, new_3, 1)

with open("backend/tests/test_w10_independent_verifier.py", "w", encoding="utf-8") as f:
    f.write(c)

print("Updated test_w10_independent_verifier.py")

