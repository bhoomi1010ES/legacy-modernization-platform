path = r"backend/tests/test_w04_supervisor_authority.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace("actor_id=str(owner.user_id),", "actor_id=owner_id,")
c = c.replace("actor_id=str(admin.user_id),", "actor_id=admin_id,")

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Replaced all str(owner.user_id) and str(admin.user_id)")

