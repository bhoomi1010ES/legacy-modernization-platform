path = r"backend/app/services/job_service.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = 'role_id=user.role if user.role in ("ADMIN", "SUPER_ADMIN") else "DEVELOPER",'
rep = 'role_id="DEVELOPER",'

assert target in c, "target not found in job_service.py"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated job_service.py successfully")

