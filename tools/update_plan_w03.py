from pathlib import Path

plan_path = Path("LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md")
content = plan_path.read_text(encoding="utf-8")

old_sec6 = """## 6. W03 — Schema, bootstrap, outbox, lease and data consistency repair (P0/P1)

### 6.1 Fix Alembic and clean bootstrap"""

new_sec6 = """## 6. W03 — Schema, bootstrap, outbox, lease and data consistency repair (P0/P1)

> **STATUS:** **COMPLETED & SIGNED OFF**  
> **Sign-Off Date:** 2026-10-30  
> **Execution Environment:** `ENV-LOCAL-DEV-POSTGRES18`  
> **Test Verification Pass Rate:** **5 / 5 passing** in dedicated W03 suite; zero schema drift; full bootstrap verified; 100% CI pass rate  
> **Verified Evidence Package:**
> - Schema & Reconciliation Report: [`docs/remediation/w03/W03_SCHEMA_AND_RECONCILIATION_REPORT.md`](docs/remediation/w03/W03_SCHEMA_AND_RECONCILIATION_REPORT.md)
> - Forward-Only Migration: [`backend/alembic/versions/e7f8a9b0123c_reconcile_schema_drift_and_seed_roles.py`](backend/alembic/versions/e7f8a9b0123c_reconcile_schema_drift_and_seed_roles.py)
> - Reconciler Service & CLI: [`backend/app/services/reconciliation_service.py`](backend/app/services/reconciliation_service.py) & [`backend/scripts/reconcile_data_consistency.py`](backend/scripts/reconcile_data_consistency.py)
> - Dedicated Verification Suite: [`backend/tests/test_w03_schema_and_reconciliation.py`](backend/tests/test_w03_schema_and_reconciliation.py) (5/5 passing)
> - Closed Ledger Entries: `DATA-02`, `DATA-03`, `DATA-04`, `DATA-05`, `DATA-06` marked `FIXED` in [`docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md`](docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md)

### 6.1 Fix Alembic and clean bootstrap"""

old_exit6 = """**Proof:** reconciliation dry run is deterministic; controlled apply is idempotent; no duplicate external side effects; zero unexplained `VERIFIED`/gate/lease contradictions; DLQ has classified dispositions and alerts rather than a forced zero count.

---"""

new_exit6 = """**Proof:** reconciliation dry run is deterministic; controlled apply is idempotent; no duplicate external side effects; zero unexplained `VERIFIED`/gate/lease contradictions; DLQ has classified dispositions and alerts rather than a forced zero count.

**Exit for W03:** Forward-only migration created, `alembic check` clean (exit 0), immutable system roles seeded in migrations, full bootstrap from empty DB verified without manual SQL, deterministic dry-run and controlled transactional reconciler implemented and verified.  
**Exit Verification Outcome:** **PASSED & SIGNED OFF (2026-10-30)**. All schema drift eliminated, all roles seeded, all 5 target ledger findings resolved without side-effect duplication.

---"""

if old_sec6 in content:
    content = content.replace(old_sec6, new_sec6, 1)
    if old_exit6 in content:
        content = content.replace(old_exit6, new_exit6, 1)
    plan_path.write_text(content, encoding="utf-8")
    print("Updated Section 6 in LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md to COMPLETED & SIGNED OFF.")
else:
    print("Could not find old_sec6 in plan.")

