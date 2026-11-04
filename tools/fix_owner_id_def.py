path = r"backend/tests/test_w04_supervisor_authority.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# Fix in test_supervisor_command_service_lifecycle
c = c.replace(
    "job = await _create_test_job(db, JobStatus.CREATED)\n            owner, _ = await _get_test_users(db)\n\n            # 1. StartJob",
    "job = await _create_test_job(db, JobStatus.CREATED)\n            owner, _ = await _get_test_users(db)\n            owner_id = str(owner.user_id)\n\n            # 1. StartJob"
)

# Fix in test_terminal_failed_immutability_and_authorized_recovery_flow06
c = c.replace(
    "job = await _create_test_job(db, JobStatus.FAILED)\n            owner, admin = await _get_test_users(db)\n\n            # 1. Standard commands",
    "job = await _create_test_job(db, JobStatus.FAILED)\n            owner, admin = await _get_test_users(db)\n            owner_id = str(owner.user_id)\n            admin_id = str(admin.user_id)\n\n            # 1. Standard commands"
)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Fixed owner_id definition in test_w04_supervisor_authority.py")

