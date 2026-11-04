import pathlib

p = pathlib.Path("docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md")
content = p.read_text(encoding="utf-8")

old_ui_section = """### `UI-01`: Granular Pipeline Stages Inferred from Coarse Job Status
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §A.5, §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/components/workspace/AgentExecution.tsx` (lines 80–160)
- **Verified Code:** 17 detailed stage cards and worker status chips are derived from coarse `job.status` with canned summaries, showing "Completed" when no `AgentRun` or artifact exists.
- **Reproduction Recipe:**
  1. Open frontend workspace for a job with `status = 'ANALYZING'`.
  2. Interface marks Intake as "Completed" and all 7 analysis workers with canned prose despite no worker records in the backend.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/agentExecutionFidelity.test.tsx`
- **Fix PR:** `PR-W12-TRUTHFUL-AGENT-EXECUTION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W12 Blocker)`

---

### `UI-02`: Fabricated Activity Log Timeline Events
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §A.5, §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/components/workspace/ActivityLog.tsx` (lines 142–208)
- **Verified Code:**
  ```typescript
  if (list.length === 0) {
      list.push(
          { id: 'seed-1', name: 'phase4.started', description: 'Phase 4 execution initiated...', ... },
          // ... 6 more synthetic events
      );
  }
  ```
- **Reproduction Recipe:**
  1. Create a fresh job with zero backend audit events.
  2. Open Activity Log tab. UI displays 7 fabricated historical events with fake relative timestamps.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/activityLogFidelity.test.tsx`
- **Fix PR:** `PR-W12-REMOVE-SYNTHETIC-SEED-EVENTS`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W12 Blocker)`

---

### `UI-03`: Canned Zero-Regression Claims in `JobDetail`
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/pages/JobDetail.tsx` (lines 453–457)
- **Verified Code:** Claims "Zero Regressions Observed" in static markup without checking backend verification records or test runs.
- **Reproduction Recipe:**
  1. Inspect `JobDetail.tsx` line 456.
  2. Text "Zero Regressions Observed" is hard-coded in the JSX.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/jobDetailFidelity.test.tsx`
- **Fix PR:** `PR-W12-EVIDENCE-BOUND-PROSE`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W12 Blocker)`

---

### `UI-04`: Hard-Coded Replay & Verification Prose in `GateReviewModal`
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/components/GateReviewModal.tsx` (lines 175–197)
- **Verified Code:** Claims exact deterministic replay verified and zero behavioral regressions without querying backend equivalence reports.
- **Reproduction Recipe:**
  1. Open Gate Review modal for G2 or G4.
  2. Observe static text asserting verified replay regardless of whether verification was run or failed.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/gateReviewModalFidelity.test.tsx`
- **Fix PR:** `PR-W12-EVIDENCE-BOUND-GATE-MODAL`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W12 Blocker)`

---

### `UI-05`: Fabricated Job Progress & Zero Modules Projection in Backend API
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `backend/app/api/v1/jobs.py` (lines 31–50)
- **Verified Code:**
  ```python
  def _job_to_response(job: Job) -> JobResponse:
      # Hard-codes progress to 0, 50, or 100 based on status string
      progress = 100 if job.status == "COMPLETED" else (50 if job.status == "CONVERTING" else 0)
      modules_count = 0  # Hard-coded to zero
  ```
- **Reproduction Recipe:**
  1. Query `GET /api/v1/jobs` or `GET /api/v1/jobs/{job_id}`.
  2. Progress is clamped to coarse arbitrary percentages (0, 50, 100) and `modules_count` is 0, misleading the dashboard.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase1_jobs_and_audit.py::test_job_response_real_progress`
- **Fix PR:** `PR-W12-API-REAL-PROGRESS-PROJECTION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W12 Blocker)`"""

new_ui_section = """### `UI-01`: Granular Pipeline Stages Inferred from Coarse Job Status
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §A.5, §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/components/workspace/AgentExecution.tsx`
- **Verified Code:** Replaced coarse status inference with truthful `AgentRun` lookups. If no worker `AgentRun` exists, workers render as `Pending` or `Running` with `0 / 7 completed` and canned summary prose is suppressed.
- **Reproduction Recipe:**
  1. Open frontend workspace for a job with zero specialist worker agent runs.
  2. Workers truthfully report Pending/Running with 0 / 7 completed; no fabricated completion.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/w12FrontendIntegrity.test.tsx`
- **Fix PR:** `PR-W12-TRUTHFUL-AGENT-EXECUTION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W12 (2026-11-03)`: Eliminated inferred worker and stage completion in `AgentExecution.tsx`. All 7 specialized workers, Architect, Blueprint, and Feasibility stages bind strictly to persisted `AgentRun` records; CodeWriter `SUCCEEDED` status is never mapped to `VERIFIED`. Verified by `frontend/src/tests/w12FrontendIntegrity.test.tsx`.

---

### `UI-02`: Fabricated Activity Log Timeline Events
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §A.5, §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/components/workspace/ActivityLog.tsx`
- **Verified Code:** Deleted synthetic `seed-1`..`seed-7` injection block. Implemented clean honest empty state ("No activity recorded yet for this job.") and explicit polling label (`Live · Polling active (5s)`).
- **Reproduction Recipe:**
  1. Create a fresh job with zero backend audit events.
  2. Open Activity Log tab. UI displays honest empty state without any fabricated seed events.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/w12FrontendIntegrity.test.tsx`
- **Fix PR:** `PR-W12-REMOVE-SYNTHETIC-SEED-EVENTS`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W12 (2026-11-03)`: Completely removed hard-coded `seed-1` through `seed-7` synthetic events in `ActivityLog.tsx`. Added honest empty state and explicit `Live · Polling active (5s)` indicator. Verified by `frontend/src/tests/w12FrontendIntegrity.test.tsx`.

---

### `UI-03`: Canned Zero-Regression Claims in `JobDetail`
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/pages/JobDetail.tsx`
- **Verified Code:** Replaced static zero-regression claim in JSX with dynamic evidence check bound to `job.status === 'COMPLETED'`.
- **Reproduction Recipe:**
  1. Inspect `JobDetail.tsx` Tab 7 for an uncompleted job.
  2. UI truthfully indicates verification is pending or unobserved and makes no premature parity claims.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/w12FrontendIntegrity.test.tsx`
- **Fix PR:** `PR-W12-EVIDENCE-BOUND-PROSE`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W12 (2026-11-03)`: Replaced static claim in `JobDetail.tsx` with dynamic verification status check. When verification is incomplete, UI states that equivalence claims cannot be made.

---

### `UI-04`: Hard-Coded Replay & Verification Prose in `GateReviewModal`
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `frontend/src/components/GateDetailExplanationView.tsx` & `GateReviewModal.tsx`
- **Verified Code:** Removed hardcoded fallbacks (14 modules, 42 tasks, 3 waves, 98h, 4 waivers, 42/42 fixtures). Render `EVIDENCE_UNAVAILABLE` when artifacts are missing. In `GateReviewModal.tsx`, stale gates (`isStale`) and gates lacking artifact evidence disable the approval button and display an invariant blocker alert.
- **Reproduction Recipe:**
  1. Open Gate Review modal for G3 or G4 without published deliverable artifacts or on a stale gate.
  2. Approval button is disabled and UI alerts that required deliverable evidence is missing or stale.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `frontend/src/tests/w12FrontendIntegrity.test.tsx` & `backend/tests/test_w12_workflow_projection.py`
- **Fix PR:** `PR-W12-EVIDENCE-BOUND-GATE-MODAL`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W12 (2026-11-03)`: Eliminated all fabricated fallback counts in `GateDetailExplanationView.tsx`. Enforced fail-closed approval blocking in `GateReviewModal.tsx` for stale gates (`isStale`) and missing artifacts (`EVIDENCE_UNAVAILABLE`). Verified by `frontend/src/tests/w12FrontendIntegrity.test.tsx` and `backend/tests/test_w12_workflow_projection.py`.

---

### `UI-05`: Fabricated Job Progress & Zero Modules Projection in Backend API
- **Severity:** `P1`
- **Workstream Target:** `W12`
- **Audit Sources:** Latest Oct 30 Audit §G; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `backend/app/api/v1/jobs.py` (lines 31–80)
- **Verified Code:** Implemented `get_jobs_metrics(db, jobs)` in `jobs.py`. `_job_to_response` computes real persisted module counts and weighted verification progress (`verified / total`). Implemented `GET /api/v1/jobs/{job_id}/projection`.
- **Reproduction Recipe:**
  1. Query `GET /api/v1/jobs` or `GET /api/v1/jobs/{job_id}` for a job with 2 modules (1 verified).
  2. API returns `modules=2` and `progress=50` (not 0, not hardcoded 50/100).
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w12_workflow_projection.py::test_api_jobs_get_and_list_truthful_modules_and_progress`
- **Fix PR:** `PR-W12-API-REAL-PROGRESS-PROJECTION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W12 (2026-11-03)`: Replaced hardcoded `modules=0` and coarse `progress=0/50/100` in `_job_to_response` with real database queries for module count and verified module count. Created `WorkflowProjectionService` and `GET /api/v1/jobs/{job_id}/projection`. Verified by `backend/tests/test_w12_workflow_projection.py` (9/9 tests)."""

if old_ui_section in content:
    content = content.replace(old_ui_section, new_ui_section, 1)
else:
    old_crlf = old_ui_section.replace("\n", "\r\n")
    new_crlf = new_ui_section.replace("\n", "\r\n")
    assert old_crlf in content, "old_ui_section not found in REMEDIATION_EVIDENCE_LEDGER.md"
    content = content.replace(old_crlf, new_crlf, 1)

p.write_text(content, encoding="utf-8")
print("Successfully updated REMEDIATION_EVIDENCE_LEDGER.md for W12")

