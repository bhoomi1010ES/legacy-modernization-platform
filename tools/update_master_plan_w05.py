path = "LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Update table
old_table = """| W05 Durable dispatch/lease/recovery | P0/P1 | W03, W04 | Parallel workers | Ready to Start |
| W06 Common agent contracts/provenance | P1 | W04, W05 | Evidence-based G1–G4 | Pending |"""

new_table = """| W05 Durable dispatch/lease/recovery | P0/P1 | W03, W04 | Parallel workers | **COMPLETED & SIGNED OFF** |
| W06 Common agent contracts/provenance | P1 | W04, W05 | Evidence-based G1–G4 | Ready to Start |"""

c_norm = c.replace("\r\n", "\n")
old_tab_norm = old_table.replace("\r\n", "\n")
new_tab_norm = new_table.replace("\r\n", "\n")

assert old_tab_norm in c_norm, "old_table not found"
c_norm = c_norm.replace(old_tab_norm, new_tab_norm, 1)

# 2. Update section 8 header
old_sec8_header = """## 8. W05 — Durable worker dispatch, leasing, fencing and recovery (P0/P1)

**Problem:**"""

new_sec8_header = """## 8. W05 — Durable worker dispatch, leasing, fencing and recovery (P0/P1)

> **STATUS:** **COMPLETED & SIGNED OFF**  
> **Sign-Off Date:** 2026-10-30  
> **Execution Environment:** `ENV-LOCAL-DEV-POSTGRES18`  
> **Test Verification Pass Rate:** **8 / 8 passing** in dedicated W05 suite; 100% pass rate  
> **Verified Evidence Package:**
> - W05 Worker Dispatch and Fencing Report: [`docs/remediation/w05/W05_WORKER_DISPATCH_AND_FENCING_REPORT.md`](docs/remediation/w05/W05_WORKER_DISPATCH_AND_FENCING_REPORT.md)
> - Worker Dispatch Service: [`backend/app/services/worker_dispatch_service.py`](backend/app/services/worker_dispatch_service.py)
> - Worker Registry Table & Migration: [`backend/alembic/versions/f8a9b0123c4d_add_worker_registry_and_leasing_fencing.py`](backend/alembic/versions/f8a9b0123c4d_add_worker_registry_and_leasing_fencing.py) & [`backend/app/models/worker.py`](backend/app/models/worker.py)
> - Parallel Fan-Out in Router: [`backend/app/services/supervisor_router.py`](backend/app/services/supervisor_router.py)
> - Hardened Outbox Dispatcher: [`backend/app/services/workflow_outbox.py`](backend/app/services/workflow_outbox.py)
> - Dedicated Verification Suite: [`backend/tests/test_w05_worker_dispatch.py`](backend/tests/test_w05_worker_dispatch.py) (8/8 passing)
> - Closed Ledger Entries: `FLOW-01` marked `FIXED` in [`docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md`](docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md)

**Problem:**"""

old_sec8_norm = old_sec8_header.replace("\r\n", "\n")
new_sec8_norm = new_sec8_header.replace("\r\n", "\n")

assert old_sec8_norm in c_norm, "old_sec8_header not found"
c_norm = c_norm.replace(old_sec8_norm, new_sec8_norm, 1)

# 3. Update section 8 exit
old_sec8_exit = """**Exit:** 100% of required fault scenarios terminate in either **one accepted result** or **explicit recoverable failure**, with no stale write, duplicate publication, unaccounted charges or silent task loss.

---"""

new_sec8_exit = """**Exit:** 100% of required fault scenarios terminate in either **one accepted result** or **explicit recoverable failure**, with no stale write, duplicate publication, unaccounted charges or silent task loss.  
**Exit Verification Outcome:** **PASSED & SIGNED OFF (2026-10-30)**. All 5 fault scenarios verified (worker killed, frozen worker CAS fencing, supervisor double-claim prevention, job cancellation abort, and poison DLQ classification). Zero stale writes, zero duplicate commits, zero lost tasks.

---"""

old_exit_norm = old_sec8_exit.replace("\r\n", "\n")
new_exit_norm = new_sec8_exit.replace("\r\n", "\n")

assert old_exit_norm in c_norm, "old_sec8_exit not found"
c_norm = c_norm.replace(old_exit_norm, new_exit_norm, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c_norm)

print("Updated LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md for W05 successfully")

