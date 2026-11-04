from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1. Update deps.py (remove owner_permitted so role permissions are strictly enforced)
deps_path = ROOT / "backend" / "app" / "api" / "deps.py"
deps_text = deps_path.read_text(encoding="utf-8")

old_deps = """        # Verify membership role possesses required permission (or owner permitted lifecycle operations)
        owner_permitted = (
            job.owner_user_id == user.user_id
            and permission in ("job:read", "job:cancel", "job:pause_resume", "job:intake")
        )
        if not owner_permitted and not RBACPolicy.has_permission(membership.role_id, permission):
            raise ForbiddenException(
                f"Job membership role '{membership.role_id}' lacks required permission '{permission}'."
            )"""

strict_deps = """        # Verify membership role possesses required permission
        if not RBACPolicy.has_permission(membership.role_id, permission):
            raise ForbiddenException(
                f"Job membership role '{membership.role_id}' lacks required permission '{permission}'."
            )"""

if old_deps in deps_text:
    deps_text = deps_text.replace(old_deps, strict_deps)
else:
    old_crlf = old_deps.replace("\n", "\r\n")
    strict_crlf = strict_deps.replace("\n", "\r\n")
    deps_text = deps_text.replace(old_crlf, strict_crlf)
deps_path.write_text(deps_text, encoding="utf-8")
print("Reverted deps.py to strict RBAC role check")

# 2. Update job_service.py
job_svc_path = ROOT / "backend" / "app" / "services" / "job_service.py"
job_svc_text = job_svc_path.read_text(encoding="utf-8")

target_dev = 'role_id="DEVELOPER",'
target_replacement = '''role_id=user.role if user.role in ("ADMIN", "SUPER_ADMIN") else "DEVELOPER",'''

if target_dev in job_svc_text and target_replacement not in job_svc_text:
    job_svc_text = job_svc_text.replace(target_dev, target_replacement)
    job_svc_path.write_text(job_svc_text, encoding="utf-8")
    print("Updated job_service.py creator role logic")

# 3. Ensure test_phase1_jobs_and_audit.py asserts ADMIN for admin user alex.morgan
test_path = ROOT / "backend" / "tests" / "test_phase1_jobs_and_audit.py"
test_text = test_path.read_text(encoding="utf-8")
if 'assert membership.role_id == "DEVELOPER"' in test_text:
    test_text = test_text.replace('assert membership.role_id == "DEVELOPER"', 'assert membership.role_id == "ADMIN"')
    test_path.write_text(test_text, encoding="utf-8")
    print("Updated test_phase1_jobs_and_audit.py back to ADMIN for alex.morgan")

