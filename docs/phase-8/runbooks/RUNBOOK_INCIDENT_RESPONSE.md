# Operational Runbook: Incident Response & Workflow Recovery

> **Audience:** Site Reliability Engineers (SRE), Platform Administrators, On-Call Operators  
> **Classification:** Production Operational Runbook (Phase 8)  
> **Last Verified:** 2026-11-05  

---

## 1. Overview & Objective

This runbook provides deterministic operational procedures for diagnosing, containing, and remediating high-severity incidents across the Multi-Agent Legacy Modernization Platform:
- Supervisor workflow stalls and orphaned task leases
- Worker crashes and poisoned attempt retries
- Gate approval deadlocks and stale evidence cascades
- Sandbox execution timeouts and budget exhaustion

---

## 2. Incident Classification & Severity

| Severity | Definition | Target MTTR | Notification Channel |
|---|---|---:|---|
| **P0 - Critical** | Platform-wide conversion halt, database deadlock, or security boundary breach | < 30 mins | PagerDuty SRE Emergency |
| **P1 - Major** | Specific job stalled, worker lease starvation, or unrecovered model timeout | < 2 hours | Slack `#modernization-ops` |
| **P2 - Moderate** | Transient API failure, non-blocking gate serialization lag, or single retry failure | < 8 hours | Jira Service Desk |

---

## 3. Incident Scenarios & Standard Operating Procedures (SOP)

### SOP-01: Supervisor Workflow Stall / Deadlock

#### Symptoms
- Job remains in `CONVERTING`, `INTEGRATING`, or `ANALYZING` state for > 30 minutes with 0 active agent runs.
- `GET /api/v1/jobs/{job_id}` returns unchanged `updated_at` and `active_node`.

#### Diagnostic Steps
1. Inspect job status and blocking reasons:
   ```sql
   SELECT job_id, status, workflow_phase, active_node, blocking_reason, updated_at
   FROM jobs WHERE job_id = '<JOB_ID>';
   ```
2. Check for active or expired module leases:
   ```sql
   SELECT module_id, status, lease_owner, lease_expires_at, now()
   FROM modules
   WHERE job_id = '<JOB_ID>' AND status IN ('LEASED', 'RUNNING');
   ```

#### Remediation Procedure
1. Pause the job cleanly to prevent conflicting agent dispatches:
   ```http
   POST /api/v1/jobs/{job_id}/pause
   Content-Type: application/json
   {
     "reason": "Operator initiating lease recovery and worker reconciliation"
   }
   ```
2. Reclaim expired module leases:
   ```sql
   UPDATE modules
   SET status = 'PENDING',
       lease_owner = NULL,
       lease_expires_at = NULL,
       lease_generation = lease_generation + 1
   WHERE job_id = '<JOB_ID>'
     AND status IN ('LEASED', 'RUNNING')
     AND lease_expires_at < NOW();
   ```
3. Resume the job via supervisor command service:
   ```http
   POST /api/v1/jobs/{job_id}/resume
   Content-Type: application/json
   {
     "reason": "Leases successfully reclaimed by SRE; resuming conversion DAG"
   }
   ```

---

### SOP-02: Poisoned Module Attempt & Retry Cap Exhaustion

#### Symptoms
- Module reaches `FAILED` status after repeatedly hitting the retry limit (e.g., attempt 3 of 3).
- Job halts with blocking reason `RETRY_EXHAUSTION`.

#### Diagnostic Steps
1. Review attempt logs and failure classifications:
   ```sql
   SELECT attempt_id, attempt_number, status, failure_reason, created_at
   FROM module_attempts
   WHERE module_id = '<MODULE_ID>'
   ORDER BY attempt_number DESC;
   ```
2. Check associated agent run traces and sandbox error output:
   ```sql
   SELECT run_id, failure_reason, duration_ms, error_details
   FROM agent_runs
   WHERE module_id = '<MODULE_ID>';
   ```

#### Remediation Procedure
- **Option A (Code / Prompt Fix):**
  If failure was due to malformed LLM syntax or missing dependency import, update the target blueprint or dependency definitions, then request an audited admin retry:
  ```http
  POST /api/v1/jobs/{job_id}/retry
  Authorization: Bearer <SUPER_ADMIN_TOKEN>
  {
    "rationale": "SRE patched missing import; authorizing fresh attempt"
  }
  ```
- **Option B (Approved Waiver):**
  If the failure is a known non-critical gap covered by an external SLA, submit an audited waiver via Gate G3 review:
  ```json
  {
    "waiver_id": "WAIVE-2026-001",
    "rationale": "Legacy telemetry module deprecated; non-blocking for modernized core.",
    "approver": "lead-architect"
  }
  ```

---

### SOP-03: Stale Evidence Cascade Invalidation

#### Symptoms
- Reviewer clicks Approve on Gate G2 or G3, but receives HTTP 409 Conflict: `Artifact version changed during review. Reload the gate before deciding.`

#### Root Cause
- An upstream dependency or baseline test case was modified while the review was pending, causing cryptographic SHA-256 cascade invalidation of downstream artifacts.

#### Remediation Procedure
1. Verify the current valid artifact hashes:
   ```http
   GET /api/v1/jobs/{job_id}/gates/{gate_id}
   ```
2. Inspect the latest `JOB_REPORT` or `SYSTEM_VERIFICATION` artifact version.
3. Submit the gate decision using the exact updated `artifact_hashes` dictionary matching the live database record. Never force-override artifact hashes.

