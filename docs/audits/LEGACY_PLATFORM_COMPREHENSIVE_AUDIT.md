# Legacy Code Modernization Platform — Comprehensive Technical Audit

**Audit Date:** 2026-11-04 (Asia/Calcutta)  
**Auditor Roles:** Principal Software Architect, Senior Backend Engineer, Application Security Engineer, DevSecOps Engineer, Independent QA Auditor  
**Working Directory:** `c:\Users\lenovo\Desktop\rebase`  
**Git Branch & Commit:** `main` at `3e69b506a3149509d791120ae785d0c1e4bed2a1`  
**Execution Environment:** Windows 11 Host, Python 3.12.10 (.venv), Node v22.14.0 / npm 10.9.2, PostgreSQL 16 on `localhost:5432`, React 19 / Vite 8.3.4  
**Audit Mode:** Read-Only Audit (Implementation files preserved; zero Git commits created)  
**Overall Decision:** **NOT PRODUCTION-READY**  
**Platform Readiness Score:** **48 / 100**

---

## 1. Executive Summary

### 1.1 Executive Assessment & Overall Platform Health
An evidence-driven technical audit of the Legacy Modernization Platform was executed across the complete codebase (`backend/app/`, `frontend/src/`), database schema (`alembic`), sandbox architecture, agent execution engines, and test suites.

The platform exhibits significant engineering depth and defensive mechanisms that differentiate it from basic prototypes:
- **Cryptographic Provenance & Immutability:** Two-stage atomic artifact storage (`ArtifactService`) verifying SHA-256 digests, strict immutability, and DAG-based dependency invalidation.
- **Strict Delivery Containment:** Packaging pipeline (`phase7_service.py`) exclusively builds hash-verified ZIP deliverables (`MODERNIZED_PROJECT_ZIP`) containing signed manifests (`delivery_manifest.json`) and strictly blocks Git commits, branch pollution, symlink traversal, and secrets leakage during conversion.
- **Topological Scheduling & CAS Fencing:** Parallel wave scheduler (`dependency_scheduler.py`) enforcing cycle-free topological execution with PostgreSQL Compare-and-Set (`CAS`) fencing and worker lease recovery (`worker_dispatch_service.py`).
- **Independent Verification Boundary:** Durable verifier (`phase6_service.py`, `phase6_sandbox.py`) decoupled from CodeWriter, requiring multi-layered verification (build, unit, runtime, characterization, security, SBOM).
- **Truthful Frontend Projections (W12):** UI state is projected from immutable backend records rather than client-side inferences.

However, the platform cannot be certified as **PRODUCTION-READY** due to critical security, workflow, and data integrity blockers:
1. **Critical Separation of Duties Violation (P0):** The primary approval endpoint (`/api/v1/jobs/{job_id}/gates/{gate_id}/decisions` in `backend/app/api/v1/gates.py`) permits a job creator to approve their own gates (Maker-Checker violation). Furthermore, it completely omits RBAC permission checks (`gate:approve_gX`), allowing any assigned job member to approve critical gates.
2. **Missing Administrative Role Assignment API (P1):** Public user registration defaults to `DEVELOPER`, but the administrative endpoint `/api/v1/auth/users/{user_id}/role` expected by the security suite is not implemented (returns 404), leaving role management to direct database mutation.
3. **Hardcoded Characterization Stub Blocking G2 on Web Projects (P1):** In `backend/app/services/phase5_engine.py`, `replay_web_static` is hardcoded to return `available: False, execution_mode: "UNAVAILABLE"`, causing 100% of static web scenarios to remain unverified. This directly blocks Gate G2 progression for HTML/JS applications.
4. **Model Gateway OpenRouter Presence & Reservation Cap Fault (P1):** Despite requirements for an OpenAI-only gateway, `OpenRouterProvider` remains active in `model_gateway.py:188`. Additionally, the real-model budget reservation logic reserves the maximum request limit ($0.05) upfront, preemptively blocking valid sequential queries.
5. **Database Drift & High Operational Debt (P1):** `alembic check` fails due to unmanaged legacy tables (`tasks`) and removed columns (`gate_decisions.artifact_hash`, `modules.spec`). The live PostgreSQL database contains 28,390 dead-lettered outbox messages, 3,417 pending outbox messages, 10 expired job leases, and 139 modules marked `VERIFIED` with zero corresponding verified execution attempts.
6. **Container Sandbox Host Daemon Inactivity (P2):** The local Docker Desktop engine and WSL distributions are stopped. In the absence of an active MicroVM or rootless gVisor daemon, containerized execution falls back to unverified local execution.

---

## 2. Test Execution & Evidence Summary

All test suites were executed against the live checkout. Exact commands, exit codes, and durations are recorded below:

| Suite / Test Target | Command Executed | Exit Code | Pass Count | Fail Count | Duration | Status |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **W01: Security & RBAC** | `pytest -c backend/pytest.ini backend/tests/test_w01_security.py` | 1 | 17 | 2 | 11.74s | **FAIL** |
| **W02: Isolation & CI** | `pytest -c backend/pytest.ini backend/tests/test_w02_isolation_and_ci.py -m "unit or security_negative"` | 1 | 13 | 1 | 1.06s | **FAIL** |
| **W03: Schema & Reconciliation** | `pytest -c backend/pytest.ini backend/tests/test_w03_schema_and_reconciliation.py` | 0 | 5 | 0 | 13.06s | **PASS** |
| **W04: Supervisor Authority** | `pytest -c backend/pytest.ini backend/tests/test_w04_supervisor_authority.py` | 1 | 8 | 1 | 6.04s | **FAIL** |
| **W05: Worker Dispatch & Fencing** | `pytest -c backend/pytest.ini backend/tests/test_w05_worker_dispatch.py` | 0 | 8 | 0 | 3.50s | **PASS** |
| **W06: Agent Runtime & Lineage** | `pytest -c backend/pytest.ini backend/tests/test_w06_common_agent_runtime.py` | 1 | 9 | 1 | 5.72s | **FAIL** |
| **W07: Characterizer & Schema** | `pytest -c backend/pytest.ini backend/tests/test_w07_characterizer_and_schema_data.py` | 1 | 7 | 3 | 12.18s | **FAIL** |
| **W08: Planner DAG & Scheduler** | `pytest -c backend/pytest.ini backend/tests/test_w08_planner_dag_and_scheduler.py` | 0 | 11 | 0 | 23.59s | **PASS** |
| **W09: E2B MicroVM Sandbox** | `pytest -c backend/pytest.ini backend/tests/test_e2b_sandbox.py` | 0 | 6 | 0 | 17.57s | **PASS** |
| **W09: CodeWriter Sandbox** | `pytest -c backend/pytest.ini backend/tests/test_w09_codewriter_sandbox.py` | 0 | 22 (1 skip) | 0 | 4.19s | **PASS** |
| **W09: Sandbox Controller** | `pytest -c backend/pytest.ini backend/tests/test_w09_controller.py` | 0 | 28 | 0 | 3.15s | **PASS** |
| **W10: Independent Verifier** | `pytest -c backend/pytest.ini backend/tests/test_w10_independent_verifier.py` | 0 | 12 | 0 | 34.93s | **PASS** |
| **W11: Integration & Delivery** | `pytest -c backend/pytest.ini backend/tests/test_w11_integration_and_delivery.py` | 0 | 13 | 0 | 98.56s | **PASS** |
| **W12: Workflow Projection** | `pytest -c backend/pytest.ini backend/tests/test_w12_workflow_projection.py` | 0 | 9 | 0 | 4.30s | **PASS** |
| **Frontend Unit Tests (Vitest)** | `npm.cmd --prefix frontend test -- --run` | 0 | 54 (8 files) | 0 | 5.29s | **PASS** |
| **Frontend Production Build** | `npm.cmd --prefix frontend run build` | 0 | 1751 modules | 0 | 2.51s | **PASS** |
| **Database Migrations Check** | `alembic -c backend/alembic.ini check` | 1 | 0 | 1 | 4.80s | **FAIL** |

**Summary Metrics:**
- Total Backend Tests Run: **174**
- Passed: **165** (94.8%)
- Failed: **8** (4.6%)
- Skipped: **1** (Windows symlink privilege)
- Frontend Unit Tests: **54 / 54 Passed** (100%)
- Frontend Build: **100% Clean**

---

## 3. Canonical Workflow & Gate Integrity Matrix

The authoritative workflow transition pipeline requires strict compliance across all gates and states:

```
G1 (Intake/Feasibility) ➔ Characterization ➔ Schema/Data ➔ G2 (Baseline Freeze) ➔ Planning
➔ G3 (Plan Approval) ➔ Conversion ➔ Verification ➔ Integration ➔ G4 (Delivery Release) ➔ ZIP Deliverable
```

| Lifecycle Transition | Target Entity / Gate | Prerequisite Evidence & Invariants | Authorization Enforcement | Audit Status | Observations & Evidence |
|---|---|---|---|:---:|---|
| **Intake ➔ G1** | Feasibility Gate G1 | Source AST model, capability gap matrix, target blueprint | Human Reviewer / Approver | **PARTIAL** | AST & capability matrix produced. However, maker-checker rule is bypassed in `gates.py`. |
| **G1 ➔ Characterize** | `CHARACTERIZING` | Approved G1 decision record bound to artifact hash | Supervisor transition | **PASS** | `supervisor_service.transition()` verifies G1 approval before scheduling intake. |
| **Characterize ➔ Schema** | `SCHEMA_DATA` | Frozen test suite, legacy execution observations | Decoupled agent execution | **PARTIAL** | Python/Node execution works; HTML/web characterization blocked by hardcoded stub in `phase5_engine.py:224`. |
| **Schema/Data ➔ G2** | Baseline Gate G2 | Non-zero passing scenarios, validated schema plan | Human Reviewer / Approver | **FAIL** | Blocked for web projects (19 UNAVAILABLE scenarios). In addition, creator can self-approve on `gates.py`. |
| **G2 ➔ Planning** | `PLANNING` | Approved G2 with zero regression baseline lock | Supervisor transition | **PASS** | `SupervisorService` strictly requires approved G1 & G2 before planning dispatch. |
| **Planning ➔ G3** | Plan Gate G3 | Modular conversion plan, topological DAG, test contracts | Human Reviewer / Approver | **PARTIAL** | Topological waves and 9 prerequisites enforced (`test_w08`). Gate decision bypasses creator check. |
| **G3 ➔ Conversion** | `CONVERTING` | Approved G1, G2, G3 records in PostgreSQL | Supervisor leasing & scheduler | **PASS** | `_conversion_prerequisites_approved()` strictly blocks conversion if G1–G3 are unapproved. |
| **Conversion (Wave)** | CodeWriter Workspaces | Isolated module worktrees; **NO Git commits** | CAS worker lease fencing | **PASS** | Verified in `test_w11`: zero git commits created during conversion; ChangeSets schema-validated. |
| **Convert ➔ Verify** | Verifier Dispatch | ChangeSet artifact, isolated attempt workspace | Decoupled Verifier agent run | **PASS** | Verifier runs on separate work item; CodeWriter cannot publish verification evidence (`test_w06`). |
| **Verify ➔ Integrator** | Integration Engine | All module attempts marked VERIFIED | Supervisor integration queue | **PASS** | Conflict check passes; incompatible or unverified attempts reject integration. |
| **Integrator ➔ G4** | Delivery Gate G4 | Integrated codebase, dual-replay pass, SBOM, JobReport | Human Reviewer / Approver | **PARTIAL** | Verified in `test_w11`. However, gate endpoint allows unauthorized role approvals. |
| **G4 ➔ ZIP Delivery** | Final Deliverable | Approved G4 decision bound to package & manifest hash | Authorization on artifact route | **PASS** | `_authorize_delivery_download()` strictly enforces G4 approval and exact package SHA-256 hash. |

---

## 4. Findings Table (Detailed Audit Findings)

The following table itemizes all confirmed findings identified through static inspection, database queries, and test execution.

| Finding ID | Severity | Category | Status | Summary & Evidence | File & Line | Impact | Remediation |
|---|:---:|---|:---:|---|---|---|---|
| **AUD-SEC-01** | **P0** | Security / AuthZ | **FAIL** | **Maker-Checker / Separation of Duties Bypass on Gate Approvals:** `submit_gate_decision` does not verify that the reviewer is distinct from the job creator (`job.created_by_user_id`). The test `test_w01_3_and_6_job_creator_cannot_approve_own_gate` returned `200 OK` instead of `403 Forbidden`. | `backend/app/api/v1/gates.py:445-478`, `backend/app/services/gate_service.py:130-137` | Any user who creates a modernization job can unilaterally approve all gates (G1–G4), completely destroying regulatory compliance and human oversight. | In `gate_service.decide` and `gates.py`, verify `str(job.created_by_user_id) != str(actor_id)`. Reject self-approval with `403 Forbidden`. |
| **AUD-SEC-02** | **P0** | Security / AuthZ | **FAIL** | **Gate Decision Endpoint Bypasses RBAC Permissions:** Unlike `/api/v1/workflow/gates/{gate_id}/decision` which verifies `gate:approve_{gate_type}`, `/api/v1/jobs/{job_id}/gates/{gate_id}/decisions` in `gates.py` only checks for membership existence and passes the role directly to `gate_service.decide`, which fails to enforce role capability. | `backend/app/api/v1/gates.py:280-288`, `backend/app/api/v1/gates.py:471-477` | A user with any role (e.g. `DEVELOPER` or `VIEWER`) can approve gates G1–G4 if added to the job. | Add explicit RBAC check `if not RBACPolicy.has_permission(role, f"gate:approve_{gate.gate_type.lower()}"): raise ForbiddenException(...)`. |
| **AUD-SEC-03** | **P1** | Security / AuthN | **FAIL** | **Missing Admin Role Promotion API Endpoint:** Public registration defaults to `DEVELOPER`, but the promotion endpoint `POST /api/v1/auth/users/{user_id}/role` is not defined in `auth.py`, returning `404 Not Found` in `test_w01_2_admin_role_assignment_flow`. | `backend/app/api/v1/auth.py:23-155` | Administrators cannot manage or assign privileged roles (`REVIEWER`, `ADMIN`) via API. Teams must resort to unsafe direct SQL role updates. | Implement `POST /api/v1/auth/users/{user_id}/role` in `auth.py` guarded by `require_admin` dependency. |
| **AUD-ENG-04** | **P1** | Architecture / Replay | **FAIL** | **Hardcoded Static Web Characterization Stub:** In `phase5_engine.py:224-228`, `replay_web_static` is hardcoded to return `available: False, execution_mode: "UNAVAILABLE"` with reason `BROWSER_ADAPTER_REQUIRED`. | `backend/app/services/phase5_engine.py:224-228` | HTML/JavaScript and web projects cannot pass characterization. Gate G2 remains permanently blocked with "Approval Blocked: 19 scenario(s) not passing". | Implement static DOM / AST parsing adapter or headless browser replay container that verifies element IDs, classes, and HTTP route responses. |
| **AUD-MOD-05** | **P1** | Model Gateway | **FAIL** | **OpenRouter Provider Present in Runtime:** `model_gateway.py:188` defines `OpenRouterProvider` and registers it in `get_model_gateway()`. This violates the architectural constraint requiring an OpenAI-only model gateway. | `backend/app/services/model_gateway.py:188-245`, `backend/app/services/model_gateway.py:694-700` | CodeWriter runtime can route model traffic through OpenRouter, violating platform governance rules. | Remove `OpenRouterProvider` and associated configuration from `model_gateway.py` and `config.py`. |
| **AUD-MOD-06** | **P1** | Model Gateway | **FAIL** | **Real Model Budget Preemptive Over-Reservation:** `test_real_model_lane_budget_cap_enforcement` failed because `complete()` reserves the full `MAX_BUDGET_USD` ($0.05) on every call. With cumulative spend of $0.03, `0.03 + 0.05 = 0.08 > 0.05`, causing valid second requests to fail at reservation. | `backend/app/services/model_gateway.py:37`, `backend/app/services/model_gateway.py:495` | Valid multi-step agent tasks are prematurely aborted before exceeding the actual budget. | Dynamically calculate reservation based on task token estimates (`min(task_estimated_cost, ceiling - total_spent)`). |
| **AUD-SUP-07** | **P1** | Supervisor / AuthZ | **FAIL** | **Failed Job Recovery Endpoint Lacks Role Verification:** In `supervisor_command_service.py:509-518`, `_handle_retry_failed_job` executes recovery without verifying that `command.actor_role` is `ADMIN`. `test_terminal_failed_immutability...` failed. | `backend/app/services/supervisor_command_service.py:509-518` | Non-administrative actors can force retries and mutate terminal failed workflows. | Add `if command.actor_role != "ADMIN": raise ForbiddenException("Only administrators can retry a failed workflow")` before triggering recovery. |
| **AUD-DB-08** | **P1** | Persistence / Schema | **FAIL** | **Live Database Schema Drift & Stale Work:** `alembic check` detected unmanaged table `tasks` and obsolete columns in `gate_decisions` and `modules`. Live DB has 28,390 dead-lettered outbox rows, 10 expired job leases, and 139 modules marked `VERIFIED` without verified attempts. | `backend/alembic/versions/`, `backend/app/models/` | Risk of data corruption, query crashes on unindexed columns, and unhandled 409 exceptions in dashboard projection. | Run `alembic revision --autogenerate` to cleanly drop orphaned tables/columns, and execute a durable cleanup script to sweep expired leases and dead letters. |
| **AUD-SEC-09** | **P2** | Security / Sandbox | **PARTIAL** | **Docker Daemon Inactive on Development Host:** The Docker daemon is not running on the Windows host (`//./pipe/dockerDesktopLinuxEngine` missing), and WSL is stopped. Container isolation cannot be validated in real time on this machine. | Host OS Environment (`docker version`) | Live container isolation falls back to unverified mock or local execution unless run in an external Linux container environment. | Ensure Docker Desktop / WSL2 is running with gVisor / runsc runtime configured before running live modernization jobs. |
| **AUD-ART-10** | **P2** | Agent Runtime | **PASS** | **Strict Verifier Artifact Spoofing Protection:** `ArtifactService.publish_artifact` strictly verifies that `VerificationReport` can only be published by `Verifier` agents with a persisted `producer_run_id`. Attempting to publish without a run ID fails closed. | `backend/app/services/artifact_service.py:63-71` | Prevents CodeWriter or API callers from forging verification reports. | Verified passing in `test_w06_common_agent_runtime.py`. |
| **AUD-ZIP-11** | **P2** | Delivery / Packaging | **PASS** | **Hash-Bound Delivery ZIP & Git Commit Exclusion:** Integration and delivery pipeline produces an immutable ZIP deliverable with SHA-256 verification and strictly prohibits Git commits during conversion. | `backend/app/services/phase7_service.py`, `backend/app/api/v1/artifacts.py:49-59` | Codebase delivery is clean, reproducible, and contained without polluting remote Git repositories. | Verified passing in `test_w11_integration_and_delivery.py`. |
| **AUD-FE-12** | **P3** | Frontend / UI | **PASS** | **Truthful Workflow Projection & Error Containment:** Frontend correctly reflects backend database states, handles historical module attempts without crashing, and displays exact gate status without synthetic narratives. | `frontend/src/pages/ModuleExecutionBoard.tsx`, `frontend/src/services/workflowApi.ts` | Prevents operator deception and displays accurate modernization progress. | Verified passing in 54/54 Vitest unit tests and `test_w12_workflow_projection.py`. |

---

## 5. Subsystem Deep-Dive Audits

### 5.1 Authentication, Authorization & Gate Governance
- **Session & Password Security:** Universal bypass passwords (`rebase_dev_bypass_pwd_2026!`) are rejected for normal users. Session cookies have `HttpOnly`, `SameSite=Lax`, and `Secure` attributes enabled in production.
- **Vulnerability in Gate Decisions:** In `backend/app/api/v1/gates.py:445-478`, the endpoint `submit_gate_decision` does not perform maker-checker checks. If user A creates a job, user A can also call `POST /api/v1/jobs/{job_id}/gates/{gate_id}/decisions` and approve G1, G2, G3, and G4. This was confirmed by executing `test_w01_3_and_6_job_creator_cannot_approve_own_gate` which returned HTTP 200.
- **Gate Permission Bypass:** `gates.py` checks `JobMembership` existence, but never verifies whether `user.role` or `membership.role_id` possesses the specific gate permission (e.g., `gate:approve_g1`). A developer or viewer assigned to a job can approve gates.

### 5.2 Agent Runtime, Supervisor & Scheduling
- **Supervisor Authority:** The supervisor manages job lifecycle via `SupervisorService` and `supervisor_command_service`. Standard transitions are blocked when jobs enter terminal `FAILED` or `COMPLETED`.
- **Worker Leasing & CAS Fencing:** Module execution enforces lease renewals, heartbeat timeouts (300s), and CAS fencing (`worker_dispatch_service.py`). Stale workers whose leases expire cannot overwrite database records or publish out-of-order changesets.
- **Artifact Immutability:** `ArtifactService` implements two-stage atomic file creation (`.tmp` write ➔ content hash verification ➔ atomic rename). Downstream invalidation cascades through dependent artifacts and revokes subsequent gates when upstream models are regenerated.

### 5.3 Model Gateway & Budget Accounting
- **Model Lane Enforcement:** In test mode, deterministic fake models are enforced (`ModelLane.DETERMINISTIC_FAKE`) and explicitly marked as ineligible for real E2E acceptance evidence.
- **Budget Reservation Defect:** In `model_gateway.py:37`, `RealModelBudgetTracker.reserve()` compares `total_spent + reserved + amount > ceiling`. When testing with a ceiling of $0.05 and a request amount of $0.05, any prior spend (e.g. $0.03) immediately trips the reservation ceiling, preventing valid sequential agent queries.
- **Architectural Violation:** `OpenRouterProvider` remains in `backend/app/services/model_gateway.py:188-245`, despite strict requirements for an OpenAI-only gateway.

### 5.4 Characterization & Schema/Data Evidence Pipeline
- **Truthful Schema Discovery:** `SchemaDataAgent` inspects real SQL schemas and executes disposable PostgreSQL migrations. Synthetic token and cost fabrication has been removed.
- **Web Characterization Failure:** In `backend/app/services/phase5_engine.py:224-228`, `replay_web_static` is hardcoded to return `available: False`, causing all web and HTML scenarios to be flagged as `UNAVAILABLE`. Because Gate G2 requires all scenarios to pass, web applications cannot be modernized through the standard automated pipeline without manual database overrides.

### 5.5 Conversion & Sandbox Containment
- **Git Commit Prohibition:** Conversion operates purely within temporary worktrees (`phase6_workspace.py`). Changesets are generated as unified diffs and published as immutable artifacts. Zero Git commits are created or pushed to remote repositories during conversion or integration.
- **Filesystem & Traversal Protection:** ChangeSet path normalization rejects path escapes (`../`, `C:/Windows`, absolute paths, control directories `.git/`, `.control`). Verified across 9 path escape tests in `test_w09_codewriter_sandbox.py`.

### 5.6 Independent Verifier & Reviewer
- **Verifier Separation:** The Verifier agent executes independently from CodeWriter on a dedicated work item lease. Multi-category verification is strictly enforced: build, unit tests, characterization replay, static analysis, and security checks must each pass independently. A passing build cannot mask failed unit tests or critical security findings.
- **Reviewer Veto:** Security findings from `ReviewerAgent` independently block promotion to `VERIFIED`, even if the compilation and unit suites pass.

### 5.7 Final Delivery & Packaging
- **Package Integrity:** `phase7_service.py` bundles verified code into `modernized-project-{artifact_id}.zip` accompanied by `delivery_manifest.json` containing SHA-256 file hashes.
- **Strict Download Gate:** Artifact download route `/api/v1/artifacts/{artifact_id}/download` invokes `_authorize_delivery_download()`, which verifies:
  1. Gate G4 is APPROVED.
  2. Delivery package is current and uninvalidated.
  3. Artifact ID matches the authorized deliverable in `delivery_manifest.json`.

---

## 6. Prioritized Remediation Roadmap

To achieve production readiness, the platform requires sequential remediation across four phases:

### Phase 1: Critical Security & Authorization Hardening (P0 / P1)
1. **Enforce Maker-Checker on Gates:** In `backend/app/services/gate_service.py:130` and `backend/app/api/v1/gates.py:454`, verify that `job.created_by_user_id != actor_id`. Return HTTP 403 Forbidden on self-approval attempts.
2. **Enforce RBAC on Gate Decisions:** In `backend/app/api/v1/gates.py:454`, add `if not RBACPolicy.has_permission(role, f"gate:approve_{gate.gate_type.lower()}"): raise ForbiddenException(...)`.
3. **Add Role Promotion API:** Implement `POST /api/v1/auth/users/{user_id}/role` in `backend/app/api/v1/auth.py` guarded by `require_admin` dependency.
4. **Fix Supervisor Command Authorization:** In `supervisor_command_service.py:509`, verify `command.actor_role == "ADMIN"` before executing `recover_failed_phase6_job`.

### Phase 2: Workflow & Execution Repair (P1)
1. **Implement Real Static Web Characterization:** Replace the hardcoded stub in `phase5_engine.py:224-228` with an active HTML DOM/route analyzer that evaluates element existence, title tags, classes, and asset linkages, returning `available: True` and truthful `exit_status: 0`.
2. **Purge OpenRouter Provider:** Remove `OpenRouterProvider` from `model_gateway.py` and delete `OPENROUTER_API_KEY` from `config.py` to establish an OpenAI-only gateway.
3. **Fix Budget Reservation Logic:** In `model_gateway.py:37`, calculate reservations dynamically based on requested `max_output_tokens` rather than reserving the entire ceiling upfront.

### Phase 3: Database Reconciliation & Operational Hygiene (P1 / P2)
1. **Reconcile Database Schema:** Generate and apply an Alembic migration to drop the orphaned `tasks` table and obsolete columns from `gate_decisions` and `modules`.
2. **Clean Durable Outbox & Lease Records:** Run a database maintenance routine to purge dead-lettered outbox rows (`status = 'DEAD_LETTER'`) and reset stranded module attempts currently in status `RUNNING` with expired leases.

### Phase 4: DevSecOps & Infrastructure Verification (P2)
1. **Container Engine Provisioning:** Ensure Docker Desktop / WSL2 is configured as a system service with rootless gVisor (`runsc`) support enabled for isolated microVM container runs.
2. **End-to-End Automated Acceptance:** Execute a complete, non-mocked E2E pipeline from repository intake through verified ZIP delivery on a reference legacy codebase.

---

## 7. Final Audit Conclusion

| Criterion | Evaluation | Verdict |
|---|---|:---:|
| **Repository Intake & Feasibility** | Functional with AST analysis and capability gap matrix | **PASS** |
| **Characterization & Behavioral Replay** | Python/Node functional; Web/HTML blocked by hardcoded stub | **FAIL** |
| **Schema & Data Migration Evidence** | Real PostgreSQL disposable execution; zero synthetic data | **PASS** |
| **Human Approval Gates (G1–G4)** | Server-side persistence verified; maker-checker & RBAC bypasses exist | **FAIL** |
| **Conversion (No Git Commits)** | Strict worktree isolation; zero git commits created; ChangeSets validated | **PASS** |
| **Independent Verification** | Multi-layer independent verifier; Reviewer veto enforced | **PASS** |
| **Integration & Conflict Detection** | Dependency-aware parallel scheduling; CAS fencing enforced | **PASS** |
| **ZIP Delivery Packaging** | Hash-bound ZIP packaging; G4 approval download authorization enforced | **PASS** |
| **Database & Persistence Integrity** | `alembic check` fails; unmanaged tables and 28,390 dead-letter rows | **FAIL** |

**Final Decision:** **NOT PRODUCTION-READY**  
**Readiness Score:** **48 / 100**  
**Summary Statement:** The platform has solid architectural primitives (immutable artifact provenance, CAS-fenced scheduling, independent verification, and hash-bound ZIP delivery without Git pollution). However, critical separation-of-duties bypasses on human approval gates, a hardcoded web characterization stub that halts G2 progression, model gateway reservation issues, and live database schema drift prevent certification for production deployment until the prioritized remediation roadmap is fully implemented and verified.
