# Workstream W05 — Durable Worker Dispatch, Leasing, Fencing and Recovery Report

**Execution Date:** 2026-10-30  
**Status:** `COMPLETED & SIGNED OFF`  
**Execution Environment:** `ENV-LOCAL-DEV-POSTGRES18`  
**Baseline Git Commit:** `3e69b506a3149509d791120ae785d0c1e4bed2a1`  
**Target Ledger Findings:** `FLOW-01`, `DATA-04`, `DATA-05`  
**Verification Suite:** [`backend/tests/test_w05_worker_dispatch.py`](file:///C:/Users/lenovo/Desktop/rebase/backend/tests/test_w05_worker_dispatch.py) (**8/8 tests passed, 100%**)

---

## 1. Executive Summary

Workstream **W05** resolves the core concurrency, leasing, fencing, and recovery vulnerabilities of worker execution in the Legacy Modernization Platform.

Prior to W05:
1. **Serial Execution (`FLOW-01`):** The supervisor router evaluated ready modules in Wave 1 and picked only `ready_modules[0]`, serializing conversion despite independent DAG dependencies and parallel capacity.
2. **Stale Worker Commits (`DATA-04`):** If a worker claimed a task, encountered a pause/freeze, and exceeded its lease duration, it could wake up and overwrite the results of a newly assigned worker because database commits did not enforce an atomic Compare-and-Set (CAS) fence on monotonic lease generation and expiration.
3. **Outbox Stranding & DLQ Blindspots (`DATA-05`):** The outbox dispatcher lacked randomized jitter, deduplication, and failure classification, causing thundering-herd retries and unclassified dead-letter poison events.

W05 establishes an end-to-end **Claim $\to$ Run $\to$ Persist $\to$ Acknowledge** protocol with atomic CAS fencing, monotonic generation increments, unique cryptographic lease tokens, parallel DAG fan-out, and crash recovery.

---

## 2. Remediated Ledger Findings

| Finding ID | Severity | Description | Remediated Status | Verification Test / Evidence |
|---|---|---|---|---|
| **`FLOW-01`** | `P1` | Serial Module Execution in Authoritative Supervisor Router | `FIXED` | [`test_parallel_module_dispatch_flow01`](file:///C:/Users/lenovo/Desktop/rebase/backend/tests/test_w05_worker_dispatch.py) |
| **`DATA-04`** | `P1` | 24 RUNNING Module Attempts with Expired Leases & Stale Commits | `FIXED` | [`test_cas_fencing_rejects_stale_worker_after_expiry`](file:///C:/Users/lenovo/Desktop/rebase/backend/tests/test_w05_worker_dispatch.py) & `test_crash_recovery_reclaims_expired_leases` |
| **`DATA-05`** | `P1` | Stranded Outbox Events with Lack of Classification & Jitter | `FIXED` | [`test_outbox_dispatcher_deduplication_and_poison_handling`](file:///C:/Users/lenovo/Desktop/rebase/backend/tests/test_w05_worker_dispatch.py) |

---

## 3. Architectural Implementations

### 3.1 Persistent Worker Registry & Migration
- Created database table `worker_registry` via forward-only Alembic migration [`backend/alembic/versions/f8a9b0123c4d_add_worker_registry_and_leasing_fencing.py`](file:///C:/Users/lenovo/Desktop/rebase/backend/alembic/versions/f8a9b0123c4d_add_worker_registry_and_leasing_fencing.py).
- Mapped SQLAlchemy domain model [`WorkerRegistry`](file:///C:/Users/lenovo/Desktop/rebase/backend/app/models/worker.py) tracking `worker_id`, `worker_type`, `version`, `status`, `started_at`, `last_heartbeat`, and `metadata_payload`.
- Added fencing columns to `modules`: `lease_token`, `expected_input_hash`, `accepted_result_hash`, and `lease_token` to `module_attempts`.

### 3.2 Durable Worker Dispatch Service (`worker_dispatch_service.py`)
Implemented [`WorkerDispatchService`](file:///C:/Users/lenovo/Desktop/rebase/backend/app/services/worker_dispatch_service.py) delivering:
1. **Worker Lifecycle:** `register_worker`, `heartbeat_worker`, `get_active_workers`, `deregister_worker`.
2. **Atomic Task Claiming:**
   - Evaluates active capacity against `min(max_parallel_tasks, provider_concurrency_limit, sandbox_concurrency_limit)`.
   - Locks candidate modules with `SELECT ... FOR UPDATE SKIP LOCKED`.
   - Bumps monotonic `lease_generation += 1` and issues unique `lease_token`.
   - Persists `TASK_LEASED` event in `workflow_outbox` in the same transaction.
3. **Lease Renewal & Heartbeating:**
   - Verifies `lease_owner`, `lease_token`, `lease_generation`, and `lease_expires_at > now()`.
   - Rejects imposters and stale generations.
4. **Compare-and-Set (CAS) Fencing Result Commit:**
   - Atomic SQL Update:
     ```sql
     UPDATE modules
     SET status = :result_status,
         accepted_result_hash = :result_hash,
         lease_owner = NULL,
         lease_expires_at = NULL,
         lease_token = NULL,
         updated_at = now()
     WHERE module_id = :module_id
       AND status IN ('LEASED', 'RUNNING')
       AND lease_owner = :worker_id
       AND lease_generation = :lease_generation
       AND lease_expires_at > now()
       AND (lease_token = :lease_token OR lease_token IS NULL);
     ```
   - If rowcount is 0, the commit is strictly rejected with `ConflictException("Worker lease is stale or expired; result commit fenced")`. Staged files are quarantined and cannot pollute canonical storage.
5. **Crash Recovery & Stale Lease Reclamation:**
   - Scans for expired active leases (`lease_expires_at <= now()`).
   - Increments monotonic `lease_generation += 1`.
   - Marks interrupted attempts as `BLOCKED`.
   - Resets module status to `PENDING` with bumped retry count.
   - Emits `LEASE_EXPIRED_RECLAIMED` audit event and outbox event.

### 3.3 Parallel Module Fan-Out (`supervisor_router.py`)
- Enhanced [`SupervisorRouter.evaluate_next_action`](file:///C:/Users/lenovo/Desktop/rebase/backend/app/services/supervisor_router.py) to inspect all ready pending modules with satisfied DAG dependencies.
- Surfaces `ready_modules`, `ready_module_ids`, `ready_count`, `parallel_capacity`, and `parallel_fanout_eligible` in decision metadata.
- Implemented `SupervisorRouter.evaluate_parallel_actions` discovering and returning parallel task decisions up to active job concurrency limits.

### 3.4 Hardened Outbox Dispatcher (`workflow_outbox.py`)
- Added randomized jitter to bounded exponential backoff (`base_delay * random.uniform(0.75, 1.25)`).
- Implemented deduplication: skips redundant re-execution when an identical `idempotency_key` is already `PROCESSED`.
- Added failure classification on dead-lettering (`POISON_PAYLOAD`, `MAX_ATTEMPTS_EXCEEDED`, `TRANSIENT_ERROR`).
- Persists structured `OUTBOX_DEAD_LETTER` audit alert events upon dead-lettering.

---

## 4. Test Verification Matrix

All 8 tests in [`backend/tests/test_w05_worker_dispatch.py`](file:///C:/Users/lenovo/Desktop/rebase/backend/tests/test_w05_worker_dispatch.py) execute in disposable environments and passed cleanly:

| Test Name | Requirement Covered | Outcome |
|---|---|---|
| `test_worker_registry_lifecycle` | Section 8.1: Worker registry registration, heartbeat, active listing, deregistration | **PASSED** |
| `test_parallel_module_dispatch_flow01` | FLOW-01: Multi-module parallel DAG discovery and multi-task atomic claim | **PASSED** |
| `test_lease_renewal_and_stale_rejection` | Section 8.2: Valid lease heartbeat vs rejection of imposter/stale generation | **PASSED** |
| `test_cas_fencing_rejects_stale_worker_after_expiry` | DATA-04: Frozen worker commit rejected by CAS fence; successor worker succeeds | **PASSED** |
| `test_crash_recovery_reclaims_expired_leases` | Section 8.2 & 8.3: Dead worker lease reclaimed with monotonic generation bump | **PASSED** |
| `test_cancelled_job_quarantines_worker_commit` | Section 8.3: Commit rejected on cancelled terminal job; staged artifacts quarantined | **PASSED** |
| `test_outbox_dispatcher_deduplication_and_poison_handling` | DATA-05: Jitter, backoff, deduplication, and classified POISON_PAYLOAD DLQ routing | **PASSED** |
| `test_dependency_scheduler_emits_task_leased_outbox` | Section 8.2: Integration of existing DependencyScheduler with TASK_LEASED outbox | **PASSED** |

---

## 5. Sign-Off & Exit Criteria

1. **Monotonic Generation Fencing:** Proven by `test_cas_fencing_rejects_stale_worker_after_expiry`. Stale workers attempting to commit after expiration fail compare-and-set with zero database mutations.
2. **Zero Split-Brain Claims:** Proven by `test_parallel_module_dispatch_flow01` and `SKIP LOCKED` concurrency.
3. **No Silent Task Loss:** Proven by `test_crash_recovery_reclaims_expired_leases`. All expired leases are recovered with incremented generations and `BLOCKED` attempt markers.
4. **Outbox Integrity:** Proven by `test_outbox_dispatcher_deduplication_and_poison_handling`. Poison payloads are classified and isolated with structured audit alerts.

**Exit Verification Outcome:** **PASSED & SIGNED OFF (2026-10-30)**.

