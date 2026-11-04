from pathlib import Path

p = Path("docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md")
text = p.read_text(encoding="utf-8")

# Update Summary Matrix
old_matrix = """| Security & Authorization | `SEC-*` | 8 | 5 | 2 | 1 | 8 | 0 | 0 |"""
new_matrix = """| Security & Authorization | `SEC-*` | 8 | 5 | 2 | 1 | 2 | 0 | 6 (Fixed) |"""
text = text.replace(old_matrix, new_matrix)

# Update SEC-01
sec01_old = """- **Fix PR:** `PR-W01-AUTH-BYPASS-REMOVAL`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W01 Blocker)`"""

sec01_new = """- **Fix PR:** `PR-W01-AUTH-BYPASS-REMOVAL`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Universal password bypass lines removed from `backend/app/services/auth_service.py`. Enforces bcrypt hash verification. Verified by `test_w01_security.py::test_w01_1_universal_passwords_rejected_for_user_with_different_password`."""
text = text.replace(sec01_old, sec01_new)

# Update SEC-02
sec02_old = """- **Fix PR:** `PR-W01-RBAC-REGISTRATION-LOCKDOWN`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W01 Blocker)`"""

sec02_new = """- **Fix PR:** `PR-W01-RBAC-REGISTRATION-LOCKDOWN`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Included REVIEWER and APPROVER in `privileged_roles`. Enforced `DEVELOPER` default for self-registration, extra="forbid" on auth schemas, and added `POST /api/v1/auth/users/{user_id}/role` admin endpoint. Verified by `test_w01_security.py::test_w01_2_public_registration_rejects_privileged_roles` and `test_w01_2_admin_role_assignment_flow`."""
text = text.replace(sec02_old, sec02_new)

# Update SEC-03
sec03_old = """- **Fix PR:** `PR-W01-JOB-MEMBERSHIP-SEGREGATION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W01 Blocker)`"""

sec03_new = """- **Fix PR:** `PR-W01-JOB-MEMBERSHIP-SEGREGATION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: In `job_service.py`, job creators receive their global role if administrative or least-privilege `DEVELOPER`. Non-admin creators never get elevated to `ADMIN`. GateService strictly prohibits creator self-approval. Verified by `test_w01_security.py::test_w01_3_non_admin_creator_receives_developer_membership` and `test_w01_3_and_6_job_creator_cannot_approve_own_gate`."""
text = text.replace(sec03_old, sec03_new)

# Update SEC-04
sec04_old = """- **Fix PR:** `PR-W01-STACK-DETECTION-AUTH`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W01 Blocker)`"""

sec04_new = """- **Fix PR:** `PR-W01-STACK-DETECTION-AUTH`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Required `get_current_user` on `/detect-stack` and `/detect-stack/local`. Added SSRF validation rejecting loopback, link-local, and private IPs. Blocked system directory traversal in development and disabled local scanning in production. Added job authorization check. Verified by `test_w01_security.py::test_w01_4_*`."""
text = text.replace(sec04_old, sec04_new)

# Update SEC-05
sec05_old = """- **Fix PR:** `PR-W01-COOKIE-FLAGS-ENFORCEMENT`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W01 Blocker)`"""

sec05_new = """- **Fix PR:** `PR-W01-COOKIE-FLAGS-ENFORCEMENT`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Added production validators in `backend/app/core/config.py` enforcing `SESSION_COOKIE_SECURE=True` in production and rejecting wildcard allowed hosts. Registered `TrustedHostMiddleware` in `main.py`. Verified by `test_phase1_auth.py::test_cookie_security_flags`."""
text = text.replace(sec05_old, sec05_new)

# Update SEC-08
sec08_old = """- **Fix PR:** `PR-W01-HOST-AND-CSRF-HARDENING`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W01 Blocker)`"""

sec08_new = """- **Fix PR:** `PR-W01-HOST-AND-CSRF-HARDENING`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Registered `TrustedHostMiddleware` with `ALLOWED_HOSTS`. Replaced loose substring check in `csrf_protection_middleware` with exact URL/host match. Verified by `test_w01_security.py::test_w01_5_trusted_host_middleware_blocks_spoofed_hosts` and `test_w01_5_csrf_blocks_loose_substring_origin_spoofing`."""
text = text.replace(sec08_old, sec08_new)

p.write_text(text, encoding="utf-8")
print("Successfully updated REMEDIATION_EVIDENCE_LEDGER.md with W01 closure decisions")

