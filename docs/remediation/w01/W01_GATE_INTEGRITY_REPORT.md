# W01 — Gate Approval Integrity and Separation of Duties Report

> **Document Type:** Workstream Gate Architecture and Audit Integrity Report  
> **Workstream:** W01 (Emergency Authentication, Authorization & Gate Integrity)  
> **Environment:** `ENV-LOCAL-DEV-POSTGRES18` / Isolated Database `rebase_test_w01`  
> **Date:** 2026-10-30  
> **Status:** REMEDIATED & ENFORCED

---

## 1. Architectural Invariants Preserved

The gate decision subsystem is central to the platform's safety model:
1. **Single Authoritative Decision Engine:** All gate approvals and rejections across all API endpoints (`POST /api/v1/jobs/{job_id}/gates/{gate_id}/decisions` and `POST /api/v1/workflow/gates/{gate_id}/decision`) delegate exclusively to `GateService.decide` (`backend/app/services/gate_service.py:87`).
2. **Supervisor Delegation:** Approved gate transitions execute atomically through `SupervisorService.transition`, ensuring checkpoints, leases, and outbox messages advance synchronously in a single PostgreSQL transaction.
3. **Evidence Binding:** Decisions are cryptographically bound to the current versioned gate package; if `payload.artifact_hashes != gate.artifact_hashes`, decisions are rejected with `ConflictException` (409).
4. **No Synthetic Gates:** Unversioned or synthetic legacy gate identifiers are rejected.
5. **No Mutation of Historical Records:** No historical records in persistent `rebase` were altered or deleted.

---

## 2. Implemented Separation of Duties & Hardening

### 2.1 Maker-Checker Rule Enforcement

Prior to W01, if a job creator had an administrative or reviewer role, they could approve gates for their own job, eliminating independent peer review.

In `backend/app/services/gate_service.py:121–128`, a strict separation-of-duties invariant was introduced:

```python
gate = await db.scalar(select(WorkflowGate).where(WorkflowGate.gate_id == gate_id).with_for_update())
if not gate:
    raise NotFoundException("Gate", str(gate_id))
job = await db.scalar(select(Job).where(Job.job_id == gate.job_id).with_for_update())
if not job:
    raise NotFoundException("Job", str(gate.job_id))

# Separation of duties: Job creator cannot approve or reject gates for their own job (W01.6)
if job.owner_user_id and job.owner_user_id == actor_id:
    raise ForbiddenException(
        message="Separation of duties violation: job creator cannot approve or reject gates for their own job.",
        details=[ErrorDetail(field="actor_id", issue="Job creator cannot act as gate reviewer")],
    )
```

**Guarantees:**
- Even if a user is `SUPER_ADMIN` or `ADMIN`, if `job.owner_user_id == actor_id`, they are blocked from approving or rejecting any gate on that job.
- Only an independent, third-party human reviewer or administrator can decide the gate.

### 2.2 Granular Approver Capability Validation

In `backend/app/domain/state_machine.py:83–90` (`GatePolicy.validate_decision`):

```python
# Rule 2: Approver must possess an authorized role and permission
if actor_role not in cls.AUTHORIZED_APPROVER_ROLES:
    raise ForbiddenException(
        message=f"Role '{actor_role}' is not authorized to decide approval gates. Requires REVIEWER or ADMIN."
    )
if not RBACPolicy.has_permission(actor_role, f"gate:approve_{gate_type.value.lower()}"):
    raise ForbiddenException(
        message=f"Role '{actor_role}' lacks required permission 'gate:approve_{gate_type.value.lower()}'."
    )
```

Both coarse-grained role membership (`AUTHORIZED_APPROVER_ROLES`) and fine-grained capability (`gate:approve_g1` .. `g4`) are validated before evaluating evidence or rationale.

### 2.3 Concurrency & Idempotency Protection

1. **Row Locks:** `gate` and `job` rows are locked with `select(...).with_for_update()`, preventing concurrent decision overwrite races.
2. **Idempotency Key Matching:** Repeated submissions with the same `idempotency_key` verify that the decision belongs to the identical gate and reviewer (`existing.gate_id == gate_id and existing.reviewer_user_id == actor_id`).
3. **Stale Gate Decisions Rejected:** If the gate is no longer `PENDING` (status changed by an earlier decision or supervisor rollback), subsequent decisions raise `ConflictException("Gate already has terminal status...")`.

---

## 3. Test Verification Matrix

Verified in `backend/tests/test_w01_security.py::test_w01_3_and_6_job_creator_cannot_approve_own_gate`:

1. `alex.morgan@acme.corp` (admin) creates a job -> job transitions to `AWAITING_GATE_G1`.
2. `alex.morgan` submits decision on gate G1 -> **Rejected with HTTP 403 Forbidden** (`"Separation of duties violation"`).
3. Independent reviewer user is provisioned on the job.
4. Independent reviewer submits decision on gate G1 -> **Accepted with HTTP 200 OK** (`"decision": "APPROVED"`).

