path = r"backend/tests/test_phase3_supervisor.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

reviewer_func = '''async def _reviewer(db):
    owner = await _owner(db)
    reviewer = await db.scalar(select(User).where(User.user_id != owner.user_id, User.role.in_(("ADMIN", "REVIEWER"))).limit(1))
    if not reviewer:
        reviewer = User(
            user_id=uuid.uuid4(),
            email=f"reviewer_{uuid.uuid4().hex[:6]}@acme.corp",
            full_name="Reviewer Test User",
            password_hash="argon2_hash",
            role="ADMIN",
            status="ACTIVE",
        )
        db.add(reviewer)
        await db.commit()
        await db.refresh(reviewer)
    return reviewer
'''

if "async def _reviewer(db):" not in c:
    c = c.replace("async def _owner(db):", reviewer_func + "\n" + "async def _owner(db):")

c = c.replace("reviewer_id = uuid.uuid4()\n        result, decided_gate", "reviewer = await _reviewer(db)\n        result, decided_gate")
c = c.replace("actor_id=reviewer_id, actor_role=\"ADMIN\",\n        )", "actor_id=reviewer.user_id, actor_role=\"ADMIN\",\n        )")

c = c.replace("reviewer_id = uuid.uuid4()\n        first = await GateService().decide", "reviewer = await _reviewer(db)\n        first = await GateService().decide")
c = c.replace("actor_id=reviewer_id, actor_role=\"ADMIN\")", "actor_id=reviewer.user_id, actor_role=\"ADMIN\")")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated test_phase3_supervisor.py with valid DB reviewer user")

