from pathlib import Path

p = Path("LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md")
text = p.read_text(encoding="utf-8")

old_sec4 = """## 4. W01 — Emergency authentication, authorization and gate integrity (P0)

### 4.1 Universal-password and development-authentication bypass"""

new_sec4 = """## 4. W01 — Emergency authentication, authorization and gate integrity (P0)

> **STATUS:** **COMPLETED & SIGNED OFF**  
> **Sign-Off Date:** 2026-10-30  
> **Execution Environment:** `ENV-LOCAL-DEV-POSTGRES18` / Isolated Test Database `rebase_test_w01`  
> **Test Verification Pass Rate:** **41 / 41 passing** (100% across W01 security and Phase 1 regression suites)  
> **Verified Evidence Package:**
> - Security Implementation Report: [`docs/remediation/w01/W01_SECURITY_IMPLEMENTATION_REPORT.md`](docs/remediation/w01/W01_SECURITY_IMPLEMENTATION_REPORT.md)
> - Authentication Test Report: [`docs/remediation/w01/W01_AUTHENTICATION_TEST_REPORT.md`](docs/remediation/w01/W01_AUTHENTICATION_TEST_REPORT.md)
> - Authorization & RBAC Report: [`docs/remediation/w01/W01_AUTHORIZATION_AND_RBAC_REPORT.md`](docs/remediation/w01/W01_AUTHORIZATION_AND_RBAC_REPORT.md)
> - Gate Integrity Report: [`docs/remediation/w01/W01_GATE_INTEGRITY_REPORT.md`](docs/remediation/w01/W01_GATE_INTEGRITY_REPORT.md)
> - Remaining Risks & Next Workstreams: [`docs/remediation/w01/W01_REMAINING_RISKS.md`](docs/remediation/w01/W01_REMAINING_RISKS.md)
> - Dedicated Security Regression Suite: [`backend/tests/test_w01_security.py`](backend/tests/test_w01_security.py) (19/19 passing)
> - Closed Ledger Entries: `SEC-01`, `SEC-02`, `SEC-03`, `SEC-04`, `SEC-05`, `SEC-08` marked `FIXED` in [`docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md`](docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md)

### 4.1 Universal-password and development-authentication bypass"""

old_exit4 = """**Exit for W01:** All known bypass proofs fail, permissions deny by default, no unauthenticated repository scan, and **security-owner approval** of the route/policy matrix."""
new_exit4 = """**Exit for W01:** All known bypass proofs fail, permissions deny by default, no unauthenticated repository scan, and **security-owner approval** of the route/policy matrix.  
**Exit Verification Outcome:** **PASSED & SIGNED OFF (2026-10-30)**. All universal password bypass proofs fail, public registration privilege escalation blocked, creator least privilege enforced, separation of duties enforced on human gates, unauthenticated stack scanning and SSRF blocked, Host header and CSRF origin validation enforced."""

if old_sec4 in text:
    text = text.replace(old_sec4, new_sec4)
elif old_sec4.replace("\n", "\r\n") in text:
    text = text.replace(old_sec4.replace("\n", "\r\n"), new_sec4.replace("\n", "\r\n"))

if old_exit4 in text:
    text = text.replace(old_exit4, new_exit4)
elif old_exit4.replace("\n", "\r\n") in text:
    text = text.replace(old_exit4.replace("\n", "\r\n"), new_exit4.replace("\n", "\r\n"))

p.write_text(text, encoding="utf-8")
print("Successfully updated W01 status in LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md")

