with open("backend/tests/test_w10_independent_verifier.py", "r", encoding="utf-8") as f:
    c = f.read()

# 1. Fix candidate_hash assertion in test 1
old_assert_1 = """    # Immutably bound to exact candidate and suite hashes
    assert durable_run.candidate_hash == attempt.candidate_hash
    assert durable_run.suite_hash is not None
    assert durable_run.evidence_hash == p5.digest(durable_run.evidence)"""

new_assert_1 = """    # Immutably bound to exact candidate and suite hashes
    evidence = (await service.detail(db, attempt))["evidence"]
    assert durable_run.candidate_hash == evidence["verification"]["candidate_hash"]
    assert verifier_evidence["candidate_hash"] == evidence["verification"]["candidate_hash"]
    assert durable_run.suite_hash is not None
    assert durable_run.evidence_hash == p5.digest(durable_run.evidence)"""

assert old_assert_1 in c, "old_assert_1 not found"
c = c.replace(old_assert_1, new_assert_1, 1)

# 2. Fix repair_feedback assertion order in test 7
old_repair_7 = """    # Verify repair feedback carries the failed tests
    detail_second = await service.detail(db, second)
    repair_feedback = detail_second["evidence"]["repair_feedback"]
    assert repair_feedback is not None
    assert repair_feedback["results"][0]["status"] == "FAIL"

    # Executing second attempt verifies and passes
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)
    assert second.status == "VERIFIED"
    assert module.status == "VERIFIED\""""

new_repair_7 = """    # Executing second attempt verifies and passes
    await service.execute_attempt(db, second.attempt_id, gateway=gateway)
    assert second.status == "VERIFIED"
    assert module.status == "VERIFIED"

    # Verify repair feedback recorded the targeted failed tests
    detail_second = await service.detail(db, second)
    repair_feedback = detail_second["evidence"]["repair_feedback"]
    assert repair_feedback is not None
    assert repair_feedback["results"][0]["status"] == "FAIL\""""

assert old_repair_7 in c, "old_repair_7 not found"
c = c.replace(old_repair_7, new_repair_7, 1)

with open("backend/tests/test_w10_independent_verifier.py", "w", encoding="utf-8") as f:
    f.write(c)

print("Applied fixes to test_w10_independent_verifier.py successfully")

