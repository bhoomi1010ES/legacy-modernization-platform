path = r"backend/tests/test_w04_supervisor_authority.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(line)
    if "owner, _ = await _get_test_users(db)" in line:
        new_lines.append("        owner_id = str(owner.user_id)\n")
    if "owner, admin = await _get_test_users(db)" in line:
        new_lines.append("        owner_id = str(owner.user_id)\n        admin_id = str(admin.user_id)\n")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Updated test_w04_supervisor_authority.py successfully!")

