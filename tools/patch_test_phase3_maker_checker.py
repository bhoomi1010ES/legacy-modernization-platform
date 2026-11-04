path = r"backend/tests/test_phase3_supervisor.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target1 = '''        result, decided_gate, routed_job, replay = await GateService().decide(
            db, gate.gate_id,
            GateDecisionRequest(decision=DecisionOutcome.REJECTED, rationale="Coverage is missing the retry edge case.", artifact_hashes={}),
            actor_id=owner.user_id, actor_role="ADMIN",
        )'''

rep1 = '''        reviewer_id = uuid.uuid4()
        result, decided_gate, routed_job, replay = await GateService().decide(
            db, gate.gate_id,
            GateDecisionRequest(decision=DecisionOutcome.REJECTED, rationale="Coverage is missing the retry edge case.", artifact_hashes={}),
            actor_id=reviewer_id, actor_role="ADMIN",
        )'''

target2 = '''        first = await GateService().decide(db, gate.gate_id, payload, actor_id=owner.user_id, actor_role="ADMIN")
        second = await GateService().decide(db, gate.gate_id, payload, actor_id=owner.user_id, actor_role="ADMIN")
        assert first[0].decision_id == second[0].decision_id and second[3] is True
        conflicting = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED, rationale="A second reviewer attempted a stale decision.", artifact_hashes={}
        )
        with pytest.raises(ConflictException, match="already has terminal status"):
            await GateService().decide(db, gate.gate_id, conflicting, actor_id=owner.user_id, actor_role="ADMIN")'''

rep2 = '''        reviewer_id = uuid.uuid4()
        first = await GateService().decide(db, gate.gate_id, payload, actor_id=reviewer_id, actor_role="ADMIN")
        second = await GateService().decide(db, gate.gate_id, payload, actor_id=reviewer_id, actor_role="ADMIN")
        assert first[0].decision_id == second[0].decision_id and second[3] is True
        conflicting = GateDecisionRequest(
            decision=DecisionOutcome.REJECTED, rationale="A second reviewer attempted a stale decision.", artifact_hashes={}
        )
        with pytest.raises(ConflictException, match="already has terminal status"):
            await GateService().decide(db, gate.gate_id, conflicting, actor_id=reviewer_id, actor_role="ADMIN")'''

if target1 not in c:
    target1 = target1.replace("\n", "\r\n")
    rep1 = rep1.replace("\n", "\r\n")
if target2 not in c:
    target2 = target2.replace("\n", "\r\n")
    rep2 = rep2.replace("\n", "\r\n")

assert target1 in c, "target1 not found"
assert target2 in c, "target2 not found"

c = c.replace(target1, rep1, 1).replace(target2, rep2, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated test_phase3_supervisor.py for maker-checker reviewer IDs")

