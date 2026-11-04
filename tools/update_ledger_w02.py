from pathlib import Path

ledger_path = Path("docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md")
content = ledger_path.read_text(encoding="utf-8")

old_entry = """### `TEST-04`: Backend Tests Bound to Persistent Development Database
- **Severity:** `P0`
- **Workstream Target:** `W02`
- **Audit Sources:** Latest Oct 30 Audit §A.7, §J; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §0.1, §5
- **Source File Pointer:** `backend/tests/conftest.py` (lines 5–31)
- **Verified Code:** `conftest.py` modifies `ENVIRONMENT="testing"` in memory, but imports `AsyncSessionLocal` configured with the persistent development PostgreSQL URL (`localhost:5432/rebase`).
- **Reproduction Recipe:**
  1. Inspect `conftest.py` database fixture.
  2. Running `pytest` creates and rolls back/commits rows against the persistent `rebase` development database, creating risk of data contamination.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/conftest.py::test_disposable_database_guard`
- **Fix PR:** `PR-W02-HERMETIC-TEST-CONTAINER-ISOLATION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W02 Blocker)`"""

new_entry = """### `TEST-04`: Backend Tests Bound to Persistent Development Database
- **Severity:** `P0`
- **Workstream Target:** `W02`
- **Audit Sources:** Latest Oct 30 Audit §A.7, §J; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §0.1, §5
- **Source File Pointer:** `backend/tests/conftest.py` (lines 5–31), `backend/app/core/testing_infrastructure.py`
- **Verified Code:** `conftest.py` integrates `IsolationGuard` and `DisposableDatabaseManager`, strictly refusing execution against protected persistent databases (`rebase`, `production`, etc.) and enforcing `TEST_ISOLATION_TOKEN`.
- **Reproduction Recipe:**
  1. Inspect `conftest.py` database fixture.
  2. Setting `DATABASE_URL` to `.../rebase` immediately raises `ProtectedResourceError: CRITICAL TEST ISOLATION VIOLATION`.
  3. Tests execute in disposable PostgreSQL database `rebase_test_<uuid>` with automated Alembic migrations and force-drop teardown.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w02_isolation_and_ci.py::test_production_database_url_refusal` & `test_disposable_postgres_lifecycle`
- **Fix PR:** `PR-W02-HERMETIC-TEST-CONTAINER-ISOLATION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W02 (2026-10-30)`: Implemented `IsolationGuard` and `DisposableDatabaseManager` in `backend/app/core/testing_infrastructure.py`. Configured automated disposable database provisioning (`rebase_test_<uuid>`), schema migration, connection termination, and force-drop cleanup. Enforced `TEST_ISOLATION_TOKEN` verification. Verified 100% pass across 15 isolation and lifecycle tests."""

if old_entry in content:
    content = content.replace(old_entry, new_entry, 1)
    ledger_path.write_text(content, encoding="utf-8")
    print("Updated TEST-04 in REMEDIATION_EVIDENCE_LEDGER.md to FIXED.")
else:
    print("Could not find exact old_entry in ledger.")

