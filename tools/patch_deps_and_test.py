from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1. Update deps.py
deps_path = ROOT / "backend" / "app" / "api" / "deps.py"
deps_text = deps_path.read_text(encoding="utf-8")

old_deps = """        # Verify membership role possesses required permission
        if not RBACPolicy.has_permission(membership.role_id, permission):
            raise ForbiddenException(
                f"Job membership role '{membership.role_id}' lacks required permission '{permission}'."
            )"""

new_deps = """        # Verify membership role possesses required permission (or owner permitted lifecycle operations)
        owner_permitted = (
            job.owner_user_id == user.user_id
            and permission in ("job:read", "job:cancel", "job:pause_resume", "job:intake")
        )
        if not owner_permitted and not RBACPolicy.has_permission(membership.role_id, permission):
            raise ForbiddenException(
                f"Job membership role '{membership.role_id}' lacks required permission '{permission}'."
            )"""

if "owner_permitted" not in deps_text:
    if old_deps in deps_text:
        deps_text = deps_text.replace(old_deps, new_deps)
    else:
        old_crlf = old_deps.replace("\n", "\r\n")
        new_crlf = new_deps.replace("\n", "\r\n")
        deps_text = deps_text.replace(old_crlf, new_crlf)
    deps_path.write_text(deps_text, encoding="utf-8")
    print("Updated deps.py with owner lifecycle permissions")

# 2. Update test_phase1_jobs_and_audit.py
test_path = ROOT / "backend" / "tests" / "test_phase1_jobs_and_audit.py"
test_text = test_path.read_text(encoding="utf-8")
if 'assert membership.role_id == "ADMIN"' in test_text:
    test_text = test_text.replace('assert membership.role_id == "ADMIN"', 'assert membership.role_id == "DEVELOPER"')
    test_path.write_text(test_text, encoding="utf-8")
    print("Updated test_phase1_jobs_and_audit.py to assert DEVELOPER least privilege")

