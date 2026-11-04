path = r"backend/tests/test_phase3_authoritative_compliance.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = '''    admin = await _get_or_create_test_user(db, "ADMIN")
    job = Job(
        name=f"phase3-compliance-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/acme/legacy-monolith-phase3",
        owner_user_id=admin.user_id,'''

rep = '''    owner = await _get_or_create_test_user(db, "DEVELOPER")
    job = Job(
        name=f"phase3-compliance-{uuid.uuid4().hex[:8]}",
        source_repository="https://github.com/acme/legacy-monolith-phase3",
        owner_user_id=owner.user_id,'''

assert target in c, "target not found in test_phase3_authoritative_compliance.py"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated _create_test_job owner in test_phase3_authoritative_compliance.py")

