# Remediation Evidence Ledger (1:1 Issue Tracking)

> **Document Type:** Production Remediation Evidence Ledger  
> **Prepared:** 2026-10-30  
> **Baseline Commit:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` (`main`)  
> **Environment ID:** `ENV-LOCAL-DEV-POSTGRES18`  
> **Rule:** Every audit finding is reproduced, ruled out with evidence, or explicitly labeled `UNCONFIRMED`; **never silently closed**.  

---

## Summary Matrix

| Category | Prefix | Total Issues | P0 | P1 | P2 | Confirmed Reproduced | Unconfirmed | Ruled Out |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Security & Authorization | `SEC-*` | 8 | 5 | 2 | 1 | 1 | 0 | 7 (Fixed) |
| Flow & Supervisor Authority | `FLOW-*` | 7 | 4 | 3 | 0 | 0 | 0 | 7 (Fixed) |
| Data Consistency & Evidence | `DATA-*` | 7 | 4 | 3 | 0 | 0 | 0 | 7 (Fixed) |
| Verification & Testing | `TEST-*` | 5 | 3 | 2 | 0 | 0 | 0 | 5 (Fixed) |
| UI & User Presentation | `UI-*` | 5 | 0 | 5 | 0 | 5 | 0 | 0 |
| **TOTAL** | | **32** | **16** | **15** | **1** | **6** | **0** | **26 (Fixed)** |

---

## 1. Security & Authorization (`SEC-*`)

### `SEC-01`: Development Universal-Password Authentication Bypass
- **Severity:** `P0`
- **Workstream Target:** `W01`
- **Audit Sources:** Latest Oct 30 Audit §A.1, §F; Earlier Audit `Pasted text(3).txt`
- **Source File Pointer:** `backend/app/services/auth_service.py` (lines 154–157)
- **Verified Code:**
  ```python
  is_valid_pw = verify_password(password, user.password_hash) if user else False
  if user and not is_valid_pw and settings.ENVIRONMENT in ("development", "testing") and password in ("Password123!", "SecurePassword123!", "AdminSecure123!"):
      is_valid_pw = True
  ```
- **Reproduction Recipe:**
  1. Target existing administrator account (e.g., `admin@example.com`).
  2. Send `POST /api/v1/auth/login` with `{"email": "admin@example.com", "password": "Password123!"}`.
  3. Observe `200 OK` and a valid administrator session cookie returned despite wrong account password.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase1_auth.py::test_universal_password_bypass_rejection`
- **Fix PR:** `PR-W01-AUTH-BYPASS-REMOVAL`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Universal password bypass lines removed from `backend/app/services/auth_service.py`. Enforces bcrypt hash verification. Verified by `test_w01_security.py::test_w01_1_universal_passwords_rejected_for_user_with_different_password`.

---

### `SEC-02`: Public Registration Grants Protected `REVIEWER` Role
- **Severity:** `P0`
- **Workstream Target:** `W01`
- **Audit Sources:** Latest Oct 30 Audit §A.1, §F; Earlier Audit `Pasted text(3).txt`
- **Source File Pointer:** `backend/app/services/auth_service.py` (lines 80–88), `backend/app/api/v1/auth.py` (line 40)
- **Verified Code:**
  ```python
  privileged_roles = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER"}
  requested_role = (role or "DEVELOPER").strip().upper()
  if requested_role in privileged_roles and not allow_privileged:
      raise ForbiddenException(...)
  valid_roles = {"SUPER_ADMIN", "ADMIN", "PROJECT_MANAGER", "REVIEWER", "DEVELOPER", "VIEWER"}
  assigned_role = requested_role if requested_role in valid_roles else "DEVELOPER"
  ```
- **Reproduction Recipe:**
  1. Send `POST /api/v1/auth/register` with `{"email": "attacker@test.com", "full_name": "Attacker", "password": "ComplexPassword123!", "role": "REVIEWER"}`.
  2. Registration succeeds with HTTP 201; returned user role is `REVIEWER`.
  3. User can now execute human approval decisions across gates G1–G4.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase1_authorization.py::test_public_registration_cannot_request_reviewer`
- **Fix PR:** `PR-W01-RBAC-REGISTRATION-LOCKDOWN`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Included REVIEWER and APPROVER in `privileged_roles`. Enforced `DEVELOPER` default for self-registration, extra="forbid" on auth schemas, and added `POST /api/v1/auth/users/{user_id}/role` admin endpoint. Verified by `test_w01_security.py::test_w01_2_public_registration_rejects_privileged_roles` and `test_w01_2_admin_role_assignment_flow`.

---

### `SEC-03`: Job Creator Automatic `ADMIN` Self-Elevation
- **Severity:** `P0`
- **Workstream Target:** `W01`
- **Audit Sources:** Latest Oct 30 Audit §A.1, §F; Earlier Audit `Pasted text(3).txt`
- **Source File Pointer:** `backend/app/api/v1/jobs.py` (lines 191–197)
- **Verified Code:**
  ```python
  membership = JobMembership(
      membership_id=uuid.uuid4(),
      job_id=job.job_id,
      user_id=current_user.user_id,
      role="ADMIN",  # Creator always receives local ADMIN
  )
  ```
- **Reproduction Recipe:**
  1. Authenticate as any normal unprivileged developer or viewer.
  2. Send `POST /api/v1/jobs` with valid job payload.
  3. Creator is granted job-level `ADMIN`, permitting self-approval of gates G1–G4 without independent maker-checker oversight.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase1_jobs_and_audit.py::test_creator_receives_least_privilege`
- **Fix PR:** `PR-W01-JOB-MEMBERSHIP-SEGREGATION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: In `job_service.py`, job creators receive their global role if administrative or least-privilege `DEVELOPER`. Non-admin creators never get elevated to `ADMIN`. GateService strictly prohibits creator self-approval. Verified by `test_w01_security.py::test_w01_3_non_admin_creator_receives_developer_membership` and `test_w01_3_and_6_job_creator_cannot_approve_own_gate`.

---

### `SEC-04`: Anonymous Remote & Arbitrary Local Path Stack Detection
- **Severity:** `P1`
- **Workstream Target:** `W01`
- **Audit Sources:** Latest Oct 30 Audit §F
- **Source File Pointer:** `backend/app/api/v1/jobs.py` (lines 110–135, lines 215–240)
- **Verified Code:** Routes `/jobs/detect-stack` and `/jobs/detect-stack/local` omit authentication dependencies and scan arbitrary server filesystem paths.
- **Reproduction Recipe:**
  1. Call `POST /api/v1/jobs/detect-stack` without session cookie or bearer token.
  2. Pass a payload pointing to server directories.
  3. Endpoint scans the path and returns metadata without authentication.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase2_stack_detector.py::test_detect_stack_requires_authentication`
- **Fix PR:** `PR-W01-STACK-DETECTION-AUTH`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Required `get_current_user` on `/detect-stack` and `/detect-stack/local`. Added SSRF validation rejecting loopback, link-local, and private IPs. Blocked system directory traversal in development and disabled local scanning in production. Added job authorization check. Verified by `test_w01_security.py::test_w01_4_*`.

---

### `SEC-05`: Permissive Session Cookie Configuration & Missing HTTPS Enforcement
- **Severity:** `P2`
- **Workstream Target:** `W01`
- **Audit Sources:** Latest Oct 30 Audit §F; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §4.1
- **Source File Pointer:** `backend/app/core/config.py` (lines 65–68), `.env` (line 27)
- **Verified Code:**
  ```python
  SESSION_COOKIE_SECURE: bool = Field(default=False)
  SESSION_COOKIE_SAMESITE: str = Field(default="lax")
  ```
- **Reproduction Recipe:**
  1. Inspect Set-Cookie header returned on `/api/v1/auth/login`.
  2. Cookie lacks `Secure` flag.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase1_auth.py::test_cookie_security_flags`
- **Fix PR:** `PR-W01-COOKIE-FLAGS-ENFORCEMENT`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Added production validators in `backend/app/core/config.py` enforcing `SESSION_COOKIE_SECURE=True` in production and rejecting wildcard allowed hosts. Registered `TrustedHostMiddleware` in `main.py`. Verified by `test_phase1_auth.py::test_cookie_security_flags`.

---

### `SEC-06`: Production Model Secrets & Default Keys Stored in Versioned/Operational Files
- **Severity:** `P0`
- **Workstream Target:** `W01` / `W13`
- **Audit Sources:** Latest Oct 30 Audit §F; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §4.1
- **Source File Pointer:** `.env` (lines 24, 50, 51)
- **Verified Code:** Root `.env` contains plaintext active OpenAI, OpenRouter API keys and default insecure `SECRET_KEY`.
- **Reproduction Recipe:**
  1. Inspect root `.env` or `backend/.env`.
  2. Plaintext provider API keys are present on disk without external secret management or environment isolation.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_secrets_redaction.py::test_no_hardcoded_keys`
- **Fix PR:** `PR-W01-SECRET-HYGIENE-AND-REDACTION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W01 Blocker)`

---

### `SEC-07`: Unrestricted Diagnostic Artifact Upload / Privileged Output Spoofing
- **Severity:** `P0`
- **Workstream Target:** `W01`
- **Audit Sources:** Latest Oct 30 Audit §F; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §4.3
- **Source File Pointer:** `backend/app/api/v1/artifacts.py` (lines 72, 88–112)
- **Verified Code:**
  ```python
  @router.post("/jobs/{job_id}/artifacts", dependencies=[Depends(require_job_permission("artifact:read"))])
  ```
  Route requires only `artifact:read` permission to create new artifacts, allowing callers to upload synthetic `LegacyModel` or `VerificationResult` records.
- **Reproduction Recipe:**
  1. User with read-only access calls `POST /api/v1/jobs/{job_id}/artifacts`.
  2. Supplies body claiming artifact kind `VerificationResult` or `LegacyModel`.
  3. Artifact is persisted into storage and DB, spoofing authoritative outputs.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w06_common_agent_runtime.py::test_producer_spoofing_prevented`
- **Fix PR:** `PR-W01-ARTIFACT-POST-RBAC`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W06 (2026-10-30)`: Enforced server-side producer authorization in `ArtifactService.publish_artifact` (`SEC-07`). Verification evidence artifact types (`VERIFICATIONREPORT`, `EQUIVALENCEREPORT`, `TESTRESULT`, `SYSTEMVERIFICATION`, etc.) are strictly reserved for Verifier specialist agents (`producing_agent="Verifier"` / `"VerifierAgent"`) and rejected with `ForbiddenException` if attempted by `CodeWriter` or API callers. Diagnostic artifact upload endpoint requires `artifact:publish_diagnostic` and forbids all workflow-owned evidence types. Verified by `backend/tests/test_w06_common_agent_runtime.py::test_producer_spoofing_prevented`.


---

### `SEC-08`: Missing `TrustedHostMiddleware` and Ineffective Substring CSRF Match
- **Severity:** `P1`
- **Workstream Target:** `W01`
- **Audit Sources:** Latest Oct 30 Audit §F; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §4.3
- **Source File Pointer:** `backend/app/main.py` (lines 60–80)
- **Verified Code:** `CORSMiddleware` configured, but `TrustedHostMiddleware` is missing despite `ALLOWED_HOSTS` configuration in `Settings`. CSRF uses simple origin substring check.
- **Reproduction Recipe:**
  1. Send request with spoofed Host header `Host: malicious-attacker.com`.
  2. Request is processed because `TrustedHostMiddleware` is not registered.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase1_auth.py::test_trusted_host_middleware_enforced`
- **Fix PR:** `PR-W01-HOST-AND-CSRF-HARDENING`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W01 (2026-10-30)`: Registered `TrustedHostMiddleware` with `ALLOWED_HOSTS`. Replaced loose substring check in `csrf_protection_middleware` with exact URL/host match. Verified by `test_w01_security.py::test_w01_5_trusted_host_middleware_blocks_spoofed_hosts` and `test_w01_5_csrf_blocks_loose_substring_origin_spoofing`.

---

## 2. Flow & Supervisor Authority (`FLOW-*`)

### `FLOW-01`: Serial Module Execution in Authoritative Supervisor Router
- **Severity:** `P1`
- **Workstream Target:** `W04` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §A.4, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7
- **Source File Pointer:** `backend/app/services/supervisor_router.py` (lines 680–710), `backend/app/services/worker_dispatch_service.py`
- **Verified Code:** Replaced serial single-element selection in `supervisor_router.py` with multi-module parallel metadata (`ready_modules`, `parallel_capacity`, `parallel_fanout_eligible`) and added `evaluate_parallel_actions`. Implemented atomic parallel task leasing with capacity limit in `WorkerDispatchService.claim_ready_tasks`.
- **Reproduction Recipe:**
  1. Create job with 5 independent modules in Wave 1.
  2. Evaluate supervisor decision and parallel actions; verify all ready modules are discovered and multiple ready modules are claimed concurrently.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w05_worker_dispatch.py::test_parallel_module_dispatch_flow01`
- **Fix PR:** `PR-W05-PARALLEL-MODULE-FANOUT`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W05 (2026-10-30)`: Replaced single-element selection with parallel fan-out evaluation and multi-task claiming up to concurrency capacity. Monotonic lease generations and unique lease tokens issued per task. Verified by `test_w05_worker_dispatch.py::test_parallel_module_dispatch_flow01`.
---

### `FLOW-02`: Competing Orchestration Engines and Deprecated Bypass Routes
- **Severity:** `P0`
- **Workstream Target:** `W04`
- **Audit Sources:** Latest Oct 30 Audit §B, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7
- **Source File Pointer:** `backend/app/services/continuous_pipeline.py` (lines 20–80), `backend/app/services/supervisor_graph.py` (lines 384–395)
- **Verified Code:** `ContinuousPipelineService` is labeled "deprecated" but continues to be invoked by the supervisor graph for characterization, and contains direct status-changing methods.
- **Reproduction Recipe:**
  1. Inspect `supervisor_graph.py` node `characterization`.
  2. Observe delegate call to `ContinuousPipelineService._run_characterization_stage` instead of canonical agent runner.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w04_supervisor_authority.py::test_continuous_pipeline_disabled_in_production_flow02`
- **Fix PR:** `PR-W04-DEPRECATED-PIPELINE-REMOVAL`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Disabled direct `ContinuousPipelineService` invocation in production behind `ENABLE_LEGACY_CONTINUOUS_PIPELINE` feature flag. Replaced all characterization delegation in `supervisor_graph.py` with direct `capture` call. Replaced API calls in `phase6.py` and `phase7.py` with authoritative supervisor drives. Verified by `test_w04_supervisor_authority.py::test_continuous_pipeline_disabled_in_production_flow02`.

---

### `FLOW-03`: Autonomous Continuation Failure (Graph Premature Exit on Wait)
- **Severity:** `P1`
- **Workstream Target:** `W04`
- **Audit Sources:** Latest Oct 30 Audit §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7
- **Source File Pointer:** `backend/app/services/supervisor_graph.py` (lines 620–635, lines 755–758)
- **Verified Code:** `handle_wait` and `pause_for_human` route directly to `END`, terminating graph execution; recovery depends entirely on external background loops or restart hooks.
- **Reproduction Recipe:**
  1. Advance job to a pending gate or wait condition.
  2. Graph completes invocation and exits without persisting thread pause state.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w04_supervisor_authority.py::test_escalation_does_not_auto_fail_flow03`
- **Fix PR:** `PR-W04-DURABLE-GRAPH-CONTINUATION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Rewrote `node_handle_escalation` to record `WORKFLOW_ESCALATED` audit events and set blocking reasons without auto-failing jobs. Integrated `AsyncPostgresSaver` with durable interrupt at `pause_for_human` allowing resumption on the identical thread upon gate approval. Verified by `test_w04_supervisor_authority.py::test_escalation_does_not_auto_fail_flow03`.

---

### `FLOW-04`: Bundled Agent Execution in Analyzer & Characterizer
- **Severity:** `P1`
- **Workstream Target:** `W06` / `W07`
- **Audit Sources:** Latest Oct 30 Audit §B, §D; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.1
- **Source File Pointer:** `backend/app/services/phase4_orchestrator.py` (lines 400–450), `backend/app/services/phase5_service.py` (lines 341–477)
- **Verified Code:** `Phase4Orchestrator` bundles Analyzer, Architect, and Feasibility into one supervisor run; `Phase5Service` bundles Characterizer and SchemaData.
- **Reproduction Recipe:**
  1. Trace `AgentRun` records created during Phase 4.
  2. Only one coordinator run is recorded; standalone Architect and Feasibility agent runs are omitted.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w06_common_agent_runtime.py::test_decoupled_specialist_agent_runs`
- **Fix PR:** `PR-W06-AGENT-RUN-DECOUPLING`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W06 (2026-10-30)`: Decoupled bundled specialist agent execution in Phase 4. `ArchitectAgent.execute_architect` and `FeasibilityAgent.execute_feasibility` now create and record distinct `AgentRun` records in PostgreSQL with status `COMPLETED`, provider usage metrics, and link published `TargetBlueprint` and `FeasibilityReport` artifacts directly to `producer_run_id`. Verified by `backend/tests/test_w06_common_agent_runtime.py::test_decoupled_specialist_agent_runs`.


---

### `FLOW-05`: Absence of Native LangGraph Postgres Checkpointer
- **Severity:** `P0`
- **Workstream Target:** `W04`
- **Audit Sources:** Latest Oct 30 Audit §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.1 (Decision D-04)
- **Source File Pointer:** `backend/app/services/supervisor_graph.py` (line 760)
- **Verified Code:**
  ```python
  authoritative_supervisor_graph = workflow.compile()  # No checkpointer supplied
  ```
- **Reproduction Recipe:**
  1. Inspect `workflow.compile()` invocation in `supervisor_graph.py`.
  2. No `checkpointer=AsyncPostgresSaver(...)` is provided; progress is not durably checkpointed in LangGraph.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w04_supervisor_authority.py::test_langgraph_postgres_checkpointer_flow05`
- **Fix PR:** `PR-W04-LANGGRAPH-CHECKPOINTER`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Implemented `AsyncPostgresSaver` subclassing LangGraph's native `BaseCheckpointSaver`. Bound checkpoints to PostgreSQL `workflow_checkpoints` table with `thread_id=job_id` and durable interrupt before `pause_for_human`. Verified by `test_w04_supervisor_authority.py::test_langgraph_postgres_checkpointer_flow05`.

---

### `FLOW-06`: Out-of-Spec Recovery Directly Mutates Terminal `FAILED` Jobs to `CONVERTING`
- **Severity:** `P1`
- **Workstream Target:** `W04` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7
- **Source File Pointer:** `backend/app/services/supervisor_service.py` (lines 1630–1660)
- **Verified Code:** `recover_failed_phase6_job` mutates `jobs.status` from terminal `FAILED` back to `CONVERTING` without supervisor command or audit lineage.
- **Reproduction Recipe:**
  1. Job enters terminal `FAILED`.
  2. Invoke recovery helper. Job status is forcibly changed to `CONVERTING`, violating terminal state invariants.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w04_supervisor_authority.py::test_terminal_failed_immutability_and_authorized_recovery_flow06`
- **Fix PR:** `PR-W04-TERMINAL-STATE-RECOVERY`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Enforced terminal `FAILED` immutability in `JobStateMachine` and `SupervisorCommandService`. Standard commands are rejected on `FAILED` jobs; only an authorized `RetryFailedJobCommand` by `ADMIN` with minimum 10-character rationale can create a new recovery generation (`orchestration_generation += 1`) with audit trail. Verified by `test_w04_supervisor_authority.py::test_terminal_failed_immutability_and_authorized_recovery_flow06`.

---

### `FLOW-07`: Fall-Through to `SUCCESS` on Unknown Agent or Missing Inputs
- **Severity:** `P0`
- **Workstream Target:** `W04`
- **Audit Sources:** Latest Oct 30 Audit §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `backend/app/services/supervisor_graph.py` (lines 340–420)
- **Verified Code:** Nodes for Architect / Feasibility return `SUCCESS` even when legacy inputs are missing, and unmapped agent branches default to `SUCCESS`.
- **Reproduction Recipe:**
  1. Pass an unmapped agent identifier to the dispatcher node.
  2. Node returns `status: SUCCESS` rather than failing closed.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w04_supervisor_authority.py::test_unknown_agent_fails_closed_flow07`
- **Fix PR:** `PR-W04-FAIL-CLOSED-DISPATCH`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Hardened `node_execute_agent` to validate prerequisite models for Architect and Feasibility and reject unmapped agent identifiers with `execution_verdict="ESCALATE"` and `UNKNOWN_AGENT_ESCALATION` audit events. Verified by `test_w04_supervisor_authority.py::test_unknown_agent_fails_closed_flow07`.

---

## 3. Data Consistency & Evidence (`DATA-*`)

### `DATA-01`: Fabricated Schema Migration, LLM Cost, and Validation in `SchemaDataAgent`
- **Severity:** `P0`
- **Workstream Target:** `W07`
- **Audit Sources:** Latest Oct 30 Audit §A.3, §D; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `backend/app/services/schema_data_agent.py` (lines 280–310)
- **Verified Code:**
  ```python
  cost = Decimal("18.50")
  tokens = 8400
  agent_run = AgentRun(..., model_provider="anthropic", model_identifier="claude-3-5-sonnet-20241022", cost_usd=cost, ...)
  job.budget_used_usd += cost
  ```
- **Reproduction Recipe:**
  1. Trigger `SchemaDataAgent` directly.
  2. Inspect DB: agent writes Anthropic Claude 3.5 Sonnet usage, 8,400 tokens, $18.50, and reports sample validation success without calling an LLM or target DB migration.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w07_characterizer_and_schema_data.py::test_schema_data_agent_no_fabricated_costs_and_evidence_discovery` & `test_schema_data_agent_real_postgres_disposable_validation`
- **Fix PR:** `PR-W07-REAL-SCHEMA-DATA-AGENT`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W07 (2026-10-30)`: Removed fabricated $18.50 LLM cost, 8400 tokens, and fake Anthropic Claude 3.5 Sonnet usage. Converted `SchemaDataAgent` to a truthful deterministic analyzer (`AgentRun` with `model_provider="deterministic_analyzer"`, `model_identifier="ddl-schema-parser-v1"`, `cost_usd=0.0000`, `input_tokens=0`, `output_tokens=0`). Replaced hardcoded example tables (`users`, `orders`, `items`) with strict evidence-driven schema discovery from repository SQL DDL files and legacy persistence entities; returns `NO_SCHEMA_DETECTED` with 0 tables when none exist. Added real PostgreSQL 16 disposable schema validation (`validate_target_schema_disposable`) with table identifier regex validation (`^[A-Za-z_][A-Za-z0-9_]{0,62}$`), real DDL execution, constraint validation, sanitized sample insert (`sample_data_provided = True`), rollback rehearsal (`DROP TABLE ... CASCADE`), and clean teardown. Migrated artifact publication to `ArtifactService.publish_artifact`. Verified by `test_schema_data_agent_no_fabricated_costs_and_evidence_discovery` and `test_schema_data_agent_real_postgres_disposable_validation`.

---

### `DATA-02`: Alembic Schema Drift (`alembic check` Fails)
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
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Created forward-only migration `e7f8a9b0123c` reconciling indexes and seeding roles idempotently. Empty database upgrades cleanly and `alembic check` exits 0 with zero drift.

---

### `DATA-03`: 139 Modules Marked `VERIFIED` Without a Corresponding `VERIFIED` Attempt
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
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Built deterministic dry-run and controlled transactional reconciler revoking derived eligibility on unverified modules with audit event logging.

---

### `DATA-04`: 24 RUNNING Module Attempts with Expired Leases
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
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Implemented stale worker quarantine in `ReconciliationService` with automated lease clearing and failure reason tracking.

---

### `DATA-05`: Stranded Outbox Events (28,390 Dead-Letter, 2,909 Pending)
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
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Classified stranded dead-letter outbox events by root cause (poison vs transient) with explicit batch dispositioning.

---

### `DATA-06`: Workflow Gate and Job State Inconsistencies (30 Pending Gate Contradictions)
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
- **Closure Decision:** `RESOLVED_IN_W03 (2026-10-30)`: Implemented gate-job state coherence reconciliation in `ReconciliationService` transitioning contradictory gates to `INVALIDATED`.

---

### `DATA-07`: Artifact Concurrent Publication Race Condition and Storage Deletion Risk
- **Severity:** `P0`
- **Workstream Target:** `W01` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §B, §F; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §8.2
- **Source File Pointer:** `backend/app/services/artifact_service.py` (lines 38–107)
- **Verified Code:** `put_object` writes deterministic storage key before DB uniqueness transaction; on collision, compensation block calls `delete_object`, deleting the winner's file.
- **Reproduction Recipe:**
  1. Simulate two concurrent workers publishing the same artifact version.
  2. The loser's DB insert fails, triggering `delete_object(storage_key)`, which removes the winner's valid payload from disk.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w06_common_agent_runtime.py::test_concurrent_publishing_same_hash_does_not_delete_valid_file`
- **Fix PR:** `PR-W01-CONTENT-ADDRESSED-STAGING`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W06 (2026-10-30)`: Implemented two-stage atomic storage protocol in `ArtifactService.publish_artifact`. Staging key writes to `staging/{job_id}/{temp_id}.tmp`, verifies SHA-256 integrity, promotes to content-addressed final path (`jobs/{job_id}/artifacts/{type}_v{ver}_{hash[:16]}.json`), and cleans up staging. On collision or DB rollback, compensation only deletes the temporary staging key; the final storage key is never deleted, eliminating the race condition where concurrent losers delete winners' valid payloads. Verified by `backend/tests/test_w06_common_agent_runtime.py::test_concurrent_publishing_same_hash_does_not_delete_valid_file`.


---

## 4. Verification & Testing (`TEST-*`)

### `TEST-01`: Synthetic Static-Web Verification (Actual Output Fabricated from Expected)
- **Severity:** `P0`
- **Workstream Target:** `W10`
- **Audit Sources:** Latest Oct 30 Audit §A.2, §H; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `backend/app/services/phase6_sandbox.py` (lines 324–339)
- **Verified Code:**
  ```python
  if routes_ok and assets_ok:
      actual = {
          "output": case["expected"],
          "side_effects": case.get("side_effects") or {...},
      }
      match = True
  ```
- **Reproduction Recipe:**
  1. Run static-web characterization test case.
  2. Verifier sets `actual.output` equal to `case["expected"]` without evaluating adapter stdout or rendering output.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase6.py::test_no_synthetic_static_web_match` & `backend/tests/test_w10_independent_verifier.py::test_static_web_html_presence_cannot_claim_behavioral_equivalence`
- **Fix PR:** `PR-W10-REAL-STATIC-WEB-VERIFICATION`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W10 (2026-11-03)`: Replaced fabricated output logic in `phase6_sandbox.py` with truthful browser/DOM/API execution assessment. Enforces strict check profile validation, rejects synthetic match claiming, and validates DOM structure, required selectors, and script behavior. Verified by `backend/tests/test_w10_independent_verifier.py::test_static_web_html_presence_cannot_claim_behavioral_equivalence` and `backend/tests/test_phase6.py::test_no_synthetic_static_web_match`.

---

### `TEST-02`: Verification Check Commands Overstate Evidence (`compileall` as Unit/Static/Build)
- **Severity:** `P0`
- **Workstream Target:** `W10` / `W11`
- **Audit Sources:** Latest Oct 30 Audit §A.2, §H; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `.env` (lines 70, 81), `backend/app/core/config.py` (lines 36, 45)
- **Verified Code:** `PHASE6_CHECK_COMMANDS_JSON` and `PHASE7_CHECK_COMMANDS_JSON` execute `python -m compileall` under labels "unit", "static", "build", and "schema".
- **Reproduction Recipe:**
  1. Execute verification check pipeline.
  2. Observe check labeled "unit" or "static" passes while executing only byte-compilation without running `pytest`, `mypy`, or `bandit`.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase6_acceptance_gaps.py::test_real_check_commands` & `backend/tests/test_w10_independent_verifier.py::test_compileall_is_build_only_and_cannot_masquerade_as_unit_or_security`
- **Fix PR:** `PR-W10-REAL-TEST-RUNNER-COMMANDS`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W10 (2026-11-03)`: Implemented strict 9-category check profile enforcement in `sandbox_protocol.py` and `verification_profiles.py`. `python -m compileall` is strictly restricted to the `build` category and rejected if mapped to `unit`, `integration`, or `security`. Missing profile or executable fails closed as `BLOCKED` / `NOT_RUN`. Verified by `backend/tests/test_w10_independent_verifier.py::test_compileall_is_build_only_and_cannot_masquerade_as_unit_or_security` and `test_target_verification_profile_requires_all_distinct_categories`.

---

### `TEST-03`: Unavailability of SBOM Generation Tool (`syft`)
- **Severity:** `P1`
- **Workstream Target:** `W02` / `W11`
- **Audit Sources:** Latest Oct 30 Audit §B, §H, §J; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §11
- **Source File Pointer:** `.env` (line 69), `backend/app/core/config.py` (line 46)
- **Verified Code:** `PHASE7_SBOM_TOOL=syft`, but `syft` binary is absent from host system PATH.
- **Reproduction Recipe:**
  1. Run `syft --version` in terminal.
  2. Command fails with CommandNotFoundException; Phase 7 SBOM generation fails.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase7.py::test_sbom_unavailable_or_unsupported_never_claims_standard` & `backend/tests/test_w11_integration_and_delivery.py::test_missing_syft_binary_fails_closed_in_sbom_evidence`
- **Fix PR:** `PR-W11-SYFT-FAIL-CLOSED-GOVERNANCE`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W11 (2026-11-03)`: Enforced fail-closed SBOM execution in `phase7_engine.py` (`sbom_evidence`). Missing, empty, or unconfigured Syft tool fails closed as `BLOCKED` or `NOT_RUN`, blocking integration and preventing delivery ZIP publication until real `syft-json` SBOM output is generated and attested. Verified by `backend/tests/test_w11_integration_and_delivery.py::test_missing_syft_binary_fails_closed_in_sbom_evidence` and `test_fake_or_empty_sbom_blocks_integration_and_prevents_packaging`.

---

### `TEST-04`: Backend Tests Bound to Persistent Development Database
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
- **Closure Decision:** `RESOLVED_IN_W02 (2026-10-30)`: Implemented `IsolationGuard` and `DisposableDatabaseManager` in `backend/app/core/testing_infrastructure.py`. Configured automated disposable database provisioning (`rebase_test_<uuid>`), schema migration, connection termination, and force-drop cleanup. Enforced `TEST_ISOLATION_TOKEN` verification. Verified 100% pass across 15 isolation and lifecycle tests.

---

### `TEST-05`: Unconditional Feasibility Capability Readiness (Missing Probes)
- **Severity:** `P1`
- **Workstream Target:** `W07`
- **Audit Sources:** Latest Oct 30 Audit §D; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.3
- **Source File Pointer:** `backend/app/services/feasibility_agent.py` (lines 127–172)
- **Verified Code:** Unconditionally assigns status `"READY"` for TypeScript, pytest, git, and rootless sandbox without executing environment verification probes.
- **Reproduction Recipe:**
  1. Run `feasibility_agent.py` on a host without TypeScript or git.
  2. Capabilities are reported as `"READY"`, producing false feasibility approval evidence.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_w07_characterizer_and_schema_data.py::test_feasibility_agent_real_tool_probes` & `backend/tests/test_phase4_architect_and_feasibility.py::test_feasibility_agent_creates_agent_run`
- **Fix PR:** `PR-W07-FEASIBILITY-REAL-PROBES`
- **Current Status:** `FIXED`
- **Closure Decision:** `RESOLVED_IN_W07 (2026-10-30)`: Replaced unconditional `"READY"` tool capability assignments in `FeasibilityAgent.execute_feasibility` with real environment verification probes (`probe_tool` executing `shutil.which` and host subprocess `--version` calls). Tools missing from host environment (e.g. `syft`, `docker`, or missing compilers) truthfully report `status="BLOCKED"`, `installed=False`, and `evidence="Tool binary '...' not found on system PATH"`. Installed tools report `status="READY"`, `installed=True`, `version="<actual_version>"`, and execution output evidence. Verified by `backend/tests/test_w07_characterizer_and_schema_data.py::test_feasibility_agent_real_tool_probes`.

---

## 5. UI & User Presentation (`UI-*`)

### `UI-01`: Granular Pipeline Stages Inferred from Coarse Job Status
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
- **Closure Decision:** `RESOLVED_IN_W12 (2026-11-03)`: Replaced hardcoded `modules=0` and coarse `progress=0/50/100` in `_job_to_response` with real database queries for module count and verified module count. Created `WorkflowProjectionService` and `GET /api/v1/jobs/{job_id}/projection`. Verified by `backend/tests/test_w12_workflow_projection.py` (9/9 tests).

