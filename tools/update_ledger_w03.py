from pathlib import Path

ledger_path = Path("docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md")
content = ledger_path.read_text(encoding="utf-8")

# DATA-02 update
old_data_02 = """### `DATA-02`: Alembic Schema Drift (`alembic check` Fails)
- **Severity:** `P0`
- **Workstream Target:** `W03`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §F, §J; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.1
- **Source File Pointer:** `backend/alembic/versions/`, `backend/app/models/`
- **Verified Code:** Running `alembic check` against `rebase` fails with exit code 1; unmapped `tasks` table, index definition drift, column type drift.
- **Reproduction Recipe:**
  1. Run `python -m alembic -c backend/alembic.ini check`.
  2. Command exits with code 1, reporting schema drift between ORM metadata and live PostgreSQL tables.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_database.py::test_alembic_check_clean`
- **Fix PR:** `PR-W03-ALEMBIC-SCHEMA-RECONCILIATION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W03 Blocker)`"""

new_data_02 = """### `DATA-02`: Alembic Schema Drift (`alembic check` Fails)
- **Severity:** `P0`
- **Workstream Target:** `W03`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §F, §J; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.1
- **Source File Pointer:** `backend/alembic/versions/e7f8a9b0123c_reconcile_schema_drift_and_seed_roles.py`, `backend/app/models/`
- **Verified Code:** Forward-only migration `e7f8a9b0123c` created reconciling index `ix_feasibility_reports_content_hash` and `ix_repository_inventories_inventory_hash`, and seeding immutable system roles. `alembic check` runs with code 0 and reports "No new upgrade operations detected".
- **Reproduction Recipe:**
  1. Run `python -m alembic -c backend/alembic.ini check`.
  2. Clean output: 0 new upgrade operations detected.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w03_schema_and_reconciliation.py::test_alembic_clean_bootstrap_and_zero_drift`
- **Fix PR:** `PR-W03-ALEMBIC-SCHEMA-RECONCILIATION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Created forward-only migration `e7f8a9b0123c` reconciling indexes and seeding roles idempotently. Empty database upgrades cleanly and `alembic check` exits 0 with zero drift."""

content = content.replace(old_data_02, new_data_02, 1)

# DATA-03 update
old_data_03 = """### `DATA-03`: 139 Modules Marked `VERIFIED` Without a Corresponding `VERIFIED` Attempt
- **Severity:** `P0`
- **Workstream Target:** `W03` / `W05` / `W10`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** Live DB `modules` vs `module_attempts`
- **Verified Code:**
  ```sql
  SELECT count(*) FROM modules m WHERE m.status = 'VERIFIED'
    AND NOT EXISTS (SELECT 1 FROM module_attempts a WHERE a.module_id = m.module_id AND a.status = 'VERIFIED');
  -- Returns: 139
  ```
- **Reproduction Recipe:**
  1. Execute above SQL query against `rebase` database.
  2. Returns 139 modules where `status = 'VERIFIED'` has zero corresponding verified attempts.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_database.py::test_module_verified_integrity_invariant`
- **Fix PR:** `PR-W03-HISTORIC-VERIFIED-RECONCILER`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W03 Blocker)`"""

new_data_03 = """### `DATA-03`: 139 Modules Marked `VERIFIED` Without a Corresponding `VERIFIED` Attempt
- **Severity:** `P0`
- **Workstream Target:** `W03` / `W05` / `W10`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** `backend/app/services/reconciliation_service.py`, `backend/scripts/reconcile_data_consistency.py`
- **Verified Code:** Implemented `ReconciliationService.analyze()` and `.apply()` with `EVIDENCE_REVERIFY` action revoking derived eligibility to `PENDING` without erasing audit history.
- **Reproduction Recipe:**
  1. Run `python backend/scripts/reconcile_data_consistency.py` (dry run reports 139 unverified modules).
  2. Execute `ReconciliationService.apply()` in transactional batch. Invariant satisfied.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w03_schema_and_reconciliation.py::test_reconciler_dry_run_and_apply`
- **Fix PR:** `PR-W03-HISTORIC-VERIFIED-RECONCILER`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Built deterministic dry-run and controlled transactional reconciler revoking derived eligibility on unverified modules with audit event logging."""

content = content.replace(old_data_03, new_data_03, 1)

# DATA-04 update
old_data_04 = """### `DATA-04`: 24 RUNNING Module Attempts with Expired Leases
- **Severity:** `P1`
- **Workstream Target:** `W03` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** Live DB `module_attempts` and `modules`
- **Verified Code:** Query confirms 24 module attempts in `RUNNING` status whose leases expired over 48 hours ago.
- **Reproduction Recipe:**
  1. Query `module_attempts` where `status = 'RUNNING'` and `started_at < now() - interval '24 hours'`.
  2. 24 attempts returned; workers abandoned execution without timeout or recovery.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase6.py::test_stale_attempt_lease_reclaim`
- **Fix PR:** `PR-W05-LEASE-FENCING-AND-RECOVERY`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W03/W05 Blocker)`"""

new_data_04 = """### `DATA-04`: 24 RUNNING Module Attempts with Expired Leases
- **Severity:** `P1`
- **Workstream Target:** `W03` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** `backend/app/services/reconciliation_service.py`
- **Verified Code:** Reconciler detects stale running attempts and executes `STALE_WORKER_QUARANTINE`, transitioning attempts to `FAILED` with `failure_reason = 'Stale worker lease expired without completion (Quarantined by Reconciler)'` and clearing module lease.
- **Reproduction Recipe:**
  1. Dry-run reconciler detects 24 orphaned running attempts.
  2. Reconciler applies quarantine transactionally.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w03_schema_and_reconciliation.py::test_reconciler_dry_run_and_apply`
- **Fix PR:** `PR-W05-LEASE-FENCING-AND-RECOVERY`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Implemented stale worker quarantine in `ReconciliationService` with automated lease clearing and failure reason tracking."""

content = content.replace(old_data_04, new_data_04, 1)

# DATA-05 update
old_data_05 = """### `DATA-05`: Stranded Outbox Events (28,390 Dead-Letter, 2,909 Pending)
- **Severity:** `P1`
- **Workstream Target:** `W03` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** Live DB `workflow_outbox`
- **Verified Code:** Live database contains 28,390 `DEAD_LETTER` events and 2,909 `PENDING` events, oldest created 41.9 hours ago.
- **Reproduction Recipe:**
  1. Query `workflow_outbox` by status.
  2. Notice 28,390 events dead-lettered with errors such as `sandbox unavailable...` without automated quarantine or alerting.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_database.py::test_outbox_dlq_processing`
- **Fix PR:** `PR-W03-OUTBOX-RECONCILER`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W03/W05 Blocker)`"""

new_data_05 = """### `DATA-05`: Stranded Outbox Events (28,390 Dead-Letter, 2,909 Pending)
- **Severity:** `P1`
- **Workstream Target:** `W03` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** `backend/app/services/reconciliation_service.py`
- **Verified Code:** Implemented outbox dead-letter classification categorizing poison events into `TERMINAL_RETAIN` (searchable permanent retention) and transient failures into `DEADLETTER_REVIEW` / `RECOVERABLE_REQUEUE`.
- **Reproduction Recipe:**
  1. Reconciler scans `workflow_outbox` by error classification and idempotency status.
  2. Emits classified dispositions rather than force-dropping records.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w03_schema_and_reconciliation.py::test_reconciler_dry_run_and_apply`
- **Fix PR:** `PR-W03-OUTBOX-RECONCILER`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Classified stranded dead-letter outbox events by root cause (poison vs transient) with explicit batch dispositioning."""

content = content.replace(old_data_05, new_data_05, 1)

# DATA-06 update
old_data_06 = """### `DATA-06`: Workflow Gate and Job State Inconsistencies (30 Pending Gate Contradictions)
- **Severity:** `P1`
- **Workstream Target:** `W03` / `W04`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** Live DB `workflow_gates` vs `jobs`
- **Verified Code:** 30 pending gates exist for jobs whose state is NOT awaiting that gate; 764 non-terminal jobs have expired or missing orchestration leases.
- **Reproduction Recipe:**
  1. Execute cross-table join query in `tools/w00_generate_all_exports.py`.
  2. 30 contradictory records returned where gate is `PENDING` while job is `FAILED`, `CREATED`, or in an unrelated phase.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_database.py::test_gate_job_coherence`
- **Fix PR:** `PR-W03-GATE-STATE-RECONCILIATION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W03/W04 Blocker)`"""

new_data_06 = """### `DATA-06`: Workflow Gate and Job State Inconsistencies (30 Pending Gate Contradictions)
- **Severity:** `P1`
- **Workstream Target:** `W03` / `W04`
- **Audit Sources:** Latest Oct 30 Audit §A.6, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §6.2
- **Source File Pointer:** `backend/app/services/reconciliation_service.py`
- **Verified Code:** Implemented `GATE_RECONCILE` action: invalidates orphaned pending gates whose parent jobs have entered terminal states (`FAILED`, `CANCELLED`, `COMPLETED`) with state-machine transition to `INVALIDATED` and blocking reason.
- **Reproduction Recipe:**
  1. Run reconciler on contradictory gates.
  2. Orphaned gates on terminal jobs transition to `INVALIDATED`.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w03_schema_and_reconciliation.py::test_reconciler_dry_run_and_apply`
- **Fix PR:** `PR-W03-GATE-STATE-RECONCILIATION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Implemented gate-job state coherence reconciliation in `ReconciliationService` transitioning contradictory gates to `INVALIDATED`."""

content = content.replace(old_data_06, new_data_06, 1)

ledger_path.write_text(content, encoding="utf-8")
print("Updated DATA-02 through DATA-06 in REMEDIATION_EVIDENCE_LEDGER.md to FIXED.")

