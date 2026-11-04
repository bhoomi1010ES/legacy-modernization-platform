# W06 Remediation Report: Common Agent Runtime & Immutable Evidence Provenance

**Document Status:** COMPLETED & SIGNED OFF  
**Execution Date:** 2026-10-30  
**Target Workstream:** W06 (P1)  
**Target Findings:** `FLOW-04`, `DATA-07`, `SEC-07`  
**Test Suite:** `backend/tests/test_w06_common_agent_runtime.py` (10/10 passed)  
**CI Pipeline:** `tools/run_ci_checks.py` (11/11 stages passed, 109/109 tests passed)  

---

## 1. Executive Summary

Workstream W06 establishes a standardized agent runtime with immutable, content-addressed deliverable storage, normalized foreign-key lineage tracking, server-side producer authorization, decoupled specialist agent execution, and truth-in-reporting provider usage tracking.

Prior to W06:
1. **`FLOW-04`:** Analyzer, Architect, and Feasibility specialists were bundled into a single supervisor run without distinct `AgentRun` records in PostgreSQL, obscuring individual agent provenance and cost attribution.
2. **`DATA-07`:** Concurrent artifact publication suffered a critical race condition. When two workers published the same artifact version or hash, the loser's database transaction failure executed storage compensation that deleted the winner's valid file.
3. **`SEC-07`:** Unrestricted diagnostic artifact upload routes and lack of server-side producer checks allowed non-verifier agents or API callers to forge verification reports and test results (`VerificationReport`, `EquivalenceReport`).

With W06 completed:
- All deliverables are published through `ArtifactService.publish_artifact` using a **two-stage atomic storage protocol** (`staging/` write $\to$ SHA-256 verification $\to$ content-addressed final key $\to$ database transaction). Compensation on transaction failure strictly deletes only the staging key, guaranteeing that concurrent publishers never delete valid files.
- Deliverable lineage is tracked via the normalized PostgreSQL `artifact_dependencies` table with foreign key constraints. Cross-job lineage and fake ancestor provenance are strictly rejected.
- Server-side producer validation restricts verification evidence artifact types (`VERIFICATIONREPORT`, `EQUIVALENCEREPORT`, `TESTRESULT`, etc.) strictly to authorized Verifier agents (`producing_agent="Verifier"`). Attempts by `CodeWriter` or API callers to publish verification evidence are rejected with `ForbiddenException`.
- Phase 4 specialist execution is decoupled: `ArchitectAgent.execute_architect` and `FeasibilityAgent.execute_feasibility` now create and persist distinct `AgentRun` records with status `COMPLETED` and link published artifacts to `producer_run_id`.
- Provider usage metrics are tracked via separate nullable fields (`reported_input_tokens`, `reported_output_tokens`, `provider_request_id`, `provider_model_id`, `pricing_table_version`, `estimated_cost`, `billed_cost`), adhering to the rule that unknown usage is `null`, never `0`.
- Downstream invalidation traversal recursively marks revoked artifacts, dependent deliverables, and approved workflow gates as `INVALIDATED`, emitting `ARTIFACT_INVALIDATED` and `GATE_INVALIDATED` audit and outbox events.
- Prompt isolation wraps untrusted repository comments and README files in `<UNTRUSTED_REPOSITORY_INPUT>` delimiting tags, neutralizing injection attempts while `SecretRedactor` masks API keys, JWTs, and database passwords.

---

## 2. Target Remediation Ledger Findings

| ID | Title | Severity | Status | Resolution Summary |
|---|---|---|---|---|
| `FLOW-04` | Bundled Agent Execution in Analyzer & Characterizer | `P1` | **FIXED** | Decoupled Phase 4 execution in `architect_agent.py` and `feasibility_agent.py`. Distinct `AgentRun` records are persisted in PostgreSQL with status `COMPLETED` and linked to artifacts via `producer_run_id`. |
| `DATA-07` | Artifact Concurrent Publication Race Condition and Storage Deletion Risk | `P0` | **FIXED** | Implemented two-stage atomic storage protocol in `ArtifactService.publish_artifact`. Staged files write to temporary keys before promotion to content-addressed paths. Compensation strictly deletes only staging keys, preventing deletion of concurrent winning files. |
| `SEC-07` | Unrestricted Diagnostic Artifact Upload / Privileged Output Spoofing | `P0` | **FIXED** | Enforced server-side producer authorization in `ArtifactService`. Verification evidence artifacts are restricted to `Verifier` specialist agents and rejected with `ForbiddenException` when attempted by unauthorized producers. |

---

## 3. Architecture & Implementation Details

### 3.1 Two-Stage Atomic Storage Protocol (`DATA-07`)

In `ArtifactService.publish_artifact`:
1. **Stage A (Staging Write):**
   ```python
   temp_id = uuid.uuid4().hex
   staging_key = f"staging/{job_id}/{temp_id}.tmp"
   content_hash, byte_size = await self.storage.put_object(
       key=staging_key, data=content_bytes, media_type=media_type
   )
   ```
2. **Stage B (Cryptographic SHA-256 Validation):**
   ```python
   actual_hash = self.storage.compute_sha256(content_bytes)
   if actual_hash != content_hash:
       await self.storage.delete_object(staging_key)
       raise PlatformException(code="ARTIFACT_CORRUPTION_DETECTED", ...)
   ```
3. **Stage C (Content-Addressed Promotion):**
   ```python
   final_storage_key = f"jobs/{job_id}/artifacts/{artifact_type}_v{version}_{content_hash[:16]}.json"
   if not await self.storage.object_exists(final_storage_key):
       await self.storage.put_object(key=final_storage_key, data=content_bytes, media_type=media_type)
   await self.storage.delete_object(staging_key)
   ```
4. **Compensation Safety:**
   ```python
   except Exception as e:
       # Only clean up staging key; NEVER delete final_storage_key
       await self.storage.delete_object(staging_key)
       await db.rollback()
       raise PlatformException(code="ARTIFACT_CREATION_FAILED", ...)
   ```

### 3.2 Normalized Artifact Lineage Schema (`artifact_dependencies`)

Migration `a2b3c4d5e6f7_w06_artifact_lineage_and_provider_usage.py` introduced the normalized `artifact_dependencies` table:
```sql
CREATE TABLE artifact_dependencies (
    dependency_id UUID PRIMARY KEY,
    artifact_id UUID NOT NULL REFERENCES artifacts(artifact_id) ON DELETE CASCADE,
    ancestor_artifact_id UUID NOT NULL REFERENCES artifacts(artifact_id) ON DELETE RESTRICT,
    job_id UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_artifact_dependency UNIQUE (artifact_id, ancestor_artifact_id)
);
CREATE INDEX ix_artifact_dependencies_artifact_id ON artifact_dependencies (artifact_id);
CREATE INDEX ix_artifact_dependencies_ancestor_artifact_id ON artifact_dependencies (ancestor_artifact_id);
CREATE INDEX ix_artifact_dependencies_job_id ON artifact_dependencies (job_id);
```

When publishing with `derived_from`:
- Lineage references are resolved against the current job first, rejecting non-existent ancestors with `INVALID_PROVENANCE`.
- References belonging to a different job are rejected with `CROSS_JOB_LINEAGE_FORBIDDEN`.
- Ancestors marked `is_invalidated=True` are rejected with `INVALID_PROVENANCE`.
- Normalized `ArtifactDependency` records are inserted in the same transaction.

### 3.3 Server-Side Producer Authorization (`SEC-07`)

Privileged verification evidence types:
```python
VERIFICATION_ARTIFACT_TYPES = {
    "VERIFICATIONREPORT",
    "EQUIVALENCEREPORT",
    "TESTRESULT",
    "SYSTEMVERIFICATION",
    "SYSTEMVERIFICATIONREPORT",
    "COVERAGEREPORT",
}
```
If an artifact type matches `VERIFICATION_ARTIFACT_TYPES`:
- `producing_agent` MUST contain `"verifier"` or `"verification"` (case-insensitive).
- All other producers (e.g. `CodeWriter`, `IntakeAgent`, `API_USER`) raise `ForbiddenException`.

### 3.4 Decoupled Specialist Agent Runs (`FLOW-04`)

In `ArchitectAgent.execute_architect`:
- Creates and persists an independent `AgentRun(agent_name="Architect", status="COMPLETED", ...)`.
- Publishes `TargetBlueprint` artifact with `producer_run_id=architect_run.run_id`.

In `FeasibilityAgent.execute_feasibility`:
- Creates and persists an independent `AgentRun(agent_name="Feasibility", status="COMPLETED", ...)`.
- Publishes `FeasibilityReport` artifact with `producer_run_id=feasibility_run.run_id`.

### 3.5 Truth-in-Reporting Provider Usage Metrics

`AgentRun` entity in SQLAlchemy and `ModelUsage` Pydantic schema include separate, nullable columns:
- `reported_input_tokens: Optional[int]`
- `reported_output_tokens: Optional[int]`
- `provider_request_id: Optional[str]`
- `provider_model_id: Optional[str]`
- `pricing_table_version: Optional[str]`
- `estimated_cost: Optional[Decimal]`
- `billed_cost: Optional[Decimal]` (nullable; unknown usage is `null`, never `0`)

### 3.6 Downstream Invalidation Traversal

`ArtifactService.invalidate_artifact_and_downstream`:
1. Traverses the graph breadth-first using `ArtifactDependency`.
2. Marks all reachable artifacts as `is_invalidated=True`, sets `invalidated_at=utc_now()`, and records cascaded invalidation reasons.
3. Finds any `WorkflowGate` in the same job referencing any invalidated artifact and transitions its status to `INVALIDATED` with an explanatory `blocking_reason`.
4. Emits `ARTIFACT_INVALIDATED` and `GATE_INVALIDATED` audit events and outbox events for asynchronous consumer synchronization.

### 3.7 Prompt Isolation & Secret Redaction

- `isolate_untrusted_input(content, label="UNTRUSTED_REPOSITORY_INPUT")`: Wraps untrusted source repository comments, READMEs, and commit messages in `<UNTRUSTED_REPOSITORY_INPUT>` and neutralizes nested closing tags (`[ESCAPED_ISOLATION_TAG]`).
- `SecretRedactor.redact_text` / `redact_object`: Masks GitHub tokens, Anthropic/OpenAI API keys, Slack tokens, AWS credentials, private keys, JWTs, and database passwords from prompt payloads and agent traces.

---

## 4. Verification Evidence

### 4.1 W06 Dedicated Test Suite (`test_w06_common_agent_runtime.py`)

All 10 tests passed against disposable PostgreSQL in 2.97s:

```
tests/test_w06_common_agent_runtime.py::test_artifact_two_stage_atomic_publishing_and_hash_validation PASSED [ 10%]
tests/test_w06_common_agent_runtime.py::test_concurrent_publishing_same_hash_does_not_delete_valid_file PASSED [ 20%]
tests/test_w06_common_agent_runtime.py::test_artifact_lineage_and_dependencies PASSED [ 30%]
tests/test_w06_common_agent_runtime.py::test_fake_provenance_rejected PASSED [ 40%]
tests/test_w06_common_agent_runtime.py::test_cross_job_lineage_rejected PASSED [ 50%]
tests/test_w06_common_agent_runtime.py::test_deriving_from_invalidated_artifact_rejected PASSED [ 60%]
tests/test_w06_common_agent_runtime.py::test_producer_spoofing_prevented PASSED [ 70%]
tests/test_w06_common_agent_runtime.py::test_downstream_invalidation_traversal_and_gate_revocation PASSED [ 80%]
tests/test_w06_common_agent_runtime.py::test_decoupled_specialist_agent_runs PASSED [ 90%]
tests/test_w06_common_agent_runtime.py::test_prompt_isolation_and_secret_redaction PASSED [100%]
======================== 10 passed, 1 warning in 2.97s ========================
```

### 4.2 Comprehensive 11-Stage CI Pipeline Execution (`run_ci_checks.py`)

All 11 stages passed with exit code 0:

| Stage | Verification Gate | Tests / Actions | Result |
|---|---|---|---|
| **1** | Python Code Formatting (Black) | 5 core files checked | **PASSED** (0.49s) |
| **2** | Production DB Refusal Guard Proof | `IsolationGuard.verify_database_url` | **PASSED** (0.14s) |
| **3** | Hermetic Unit & Security Negative Tests | 14 unit & negative tests | **PASSED** (3.96s) |
| **4** | Disposable DB Lifecycle Integration | Disposable PostgreSQL create/drop | **PASSED** (6.96s) |
| **5** | W01 Security & Auth Regression Suite | 19 security regression tests | **PASSED** (13.86s) |
| **6** | W03 Clean Bootstrap, Drift & Reconciliation | 5 schema & reconciliation tests | **PASSED** (18.15s) |
| **7** | W04 Supervisor Authority & Command Pipeline | 9 supervisor authority tests | **PASSED** (5.11s) |
| **8** | W05 Worker Dispatch, Leasing & Fencing | 8 worker dispatch & fencing tests | **PASSED** (4.35s) |
| **9** | W06 Common Agent Runtime & Provenance | 10 agent runtime & provenance tests | **PASSED** (3.29s) |
| **10** | Frontend Unit Tests (Vitest) | 43 frontend unit tests (6 test files) | **PASSED** (4.85s) |
| **11** | Frontend Production Build (Vite) | `tsc && vite build` (1,750 modules) | **PASSED** (11.65s) |

**Total passing tests:** 109 backend & frontend tests, 0 failures, 0 regressions.

---

## 5. Artifact Manifest

| File | Purpose |
|---|---|
| `backend/app/models/artifact.py` | `ArtifactDependency` model, invalidation, schema version, and producer FKs |
| `backend/app/models/agent.py` | Provider usage columns (`reported_input_tokens`, `billed_cost`, etc.) |
| `backend/alembic/versions/a2b3c4d5e6f7_w06_artifact_lineage_and_provider_usage.py` | Migration adding `artifact_dependencies` and usage columns |
| `backend/app/services/artifact_service.py` | Two-stage atomic publish, producer authorization, dependency FKs, invalidation |
| `backend/app/services/architect_agent.py` | Decoupled `AgentRun` creation for Architect specialist |
| `backend/app/services/feasibility_agent.py` | Decoupled `AgentRun` creation for Feasibility specialist |
| `backend/app/services/agent_run_service.py` | Provider usage persistence on `AgentRun` |
| `backend/app/services/secret_redactor.py` | `isolate_untrusted_input` and credential pattern masking |
| `backend/app/schemas/artifacts.py` | Typed `ArtifactResponse` with invalidation and lineage metadata |
| `backend/app/schemas/agent_runtime.py` | Typed `ModelUsage` with provider metrics |
| `backend/tests/test_w06_common_agent_runtime.py` | Comprehensive 10-test verification suite |
| `tools/run_ci_checks.py` | 11-stage CI pipeline runner |
| `docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md` | Findings `FLOW-04`, `DATA-07`, `SEC-07` marked `FIXED` |
| `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` | Section 9 marked `COMPLETED & SIGNED OFF` |

---

## 6. Sign-Off & Next Steps

W06 has satisfied all technical criteria and exit requirements. Target findings `FLOW-04`, `DATA-07`, and `SEC-07` are fully remediated and verified.

**Next Workstream:** W07 — Real CHARACTERIZER and SCHEMA_DATA execution (P0/P1).

