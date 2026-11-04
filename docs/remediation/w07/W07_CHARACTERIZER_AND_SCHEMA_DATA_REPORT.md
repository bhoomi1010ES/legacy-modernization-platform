# W07 Remediation Report: Real CHARACTERIZER and SCHEMA_DATA Execution

**Document Status:** COMPLETED & SIGNED OFF  
**Execution Date:** 2026-10-30  
**Target Workstream:** W07 (P0/P1)  
**Target Findings:** `DATA-01`, `TEST-05`  
**Test Suite:** `backend/tests/test_w07_characterizer_and_schema_data.py` (10/10 passed)  
**Integration Suite:** `backend/tests/test_phase4_5_workflow_integration.py` (8/8 passed)  
**CI Pipeline:** `tools/run_ci_checks.py` (12/12 stages passed, 119/119 tests passed)  

---

## 1. Executive Summary

Workstream W07 eliminates fabricated schema data, synthetic passing test matches, simulated migration costs, and unverified feasibility tool readiness. It replaces synthetic shortcuts with truthful, evidence-driven discovery, real PostgreSQL 16 disposable schema validation, fail-closed DOM/route assertion checking, and real environment verification probes.

Prior to W07:
1. **`DATA-01` (P0):** `SchemaDataAgent` hardcoded an imaginary Anthropic Claude 3.5 Sonnet LLM run, billed $18.50, claimed 8,400 tokens, debited `job.budget_used_usd`, and invented tables (`users`, `orders`, `items`) when no schema was discovered.
2. **`TEST-05` (P1):** `FeasibilityAgent` unconditionally stamped tool capabilities (`typescript`, `pytest`, `git`, `rootless_sandbox`) as `"READY"` without checking whether the binaries actually existed on the host execution environment.
3. **Static-Web Fake Passing:** When web static tests lacked real workspaces or assertions failed, synthetic fallbacks reported passing status, bypassing behavioral validation.
4. **Bundled Agent Runs:** Characterizer and SchemaData executions were lumped into a single phase run rather than recorded as distinct `AgentRun` records with independent artifact references.
5. **G2 Gate Permissiveness:** G2 approval did not strictly require non-empty observed test scenarios or validated target database migration plans.

With W07 completed:
- **Zero Fabricated Costs / Truthful Deterministic Analyzer:** Removed hardcoded $18.50 cost, 8,400 tokens, and fake Anthropic run. `SchemaDataAgent` records a truthful `deterministic_analyzer` run (`model_identifier="ddl-schema-parser-v1"`) with $0.0000 cost, zero tokens, and no budget deductions.
- **Evidence-Driven Schema Discovery:** Extracts tables strictly from source repository SQL DDL files and legacy persistence definitions. Repositories without SQL return `NO_SCHEMA_DETECTED` with 0 tables. Example tables (`users`, `orders`, `items`) are **never invented**.
- **Real PostgreSQL 16 Disposable Migration Validation:** Implemented `validate_target_schema_disposable` executing in a dedicated disposable PostgreSQL schema (`schema_val_<uuid>`). It verifies table identifier regex (`^[A-Za-z_][A-Za-z0-9_]{0,62}$`), runs actual DDL statements, verifies constraints and foreign keys, inserts sanitized sample rows, performs a full rollback rehearsal (`DROP TABLE ... CASCADE`), and tears down cleanly.
- **Real Feasibility Tool Probes (`TEST-05`):** `FeasibilityAgent` executes `probe_tool` using `shutil.which` and host subprocess `--version` calls. Missing tools (e.g. `syft`, `docker`) report `BLOCKED`/`MISSING` with clear evidence; present tools report `READY` with verified versions.
- **Multi-Tier Static Web Characterization:** Categorizes static web verification into `BUILD_PASS`, `DOM_PASS`, `BEHAVIOR_PASS`, and `NOT_RUN`. Missing workspaces or HTML files return `NOT_RUN` / `UNAVAILABLE`. Required DOM IDs, CSS classes, HTML tags, and title assertions fail closed with `DOM_FAILED` and `exit_status = 1` when unmet.
- **Decoupled Agent Runs & Artifact Provenance:** `Characterizer` and `SchemaData` execute as distinct `AgentRun` records with independent `run_id`s, each linked to their respective artifacts (`BehavioralBaseline`, `SchemaPlan`) via `ArtifactService.publish_artifact`.
- **G2 Gate Readiness Invariant:** G2 readiness strictly fails closed (`ready_for_g2 = False`) if the scenario set is empty (`len(cases) == 0`) or if zero test cases pass.

---

## 2. Target Remediation Ledger Findings

| ID | Title | Severity | Status | Resolution Summary |
|---|---|---|---|---|
| `DATA-01` | Fabricated Schema Migration, LLM Cost, and Validation in `SchemaDataAgent` | `P0` | **FIXED** | Removed hardcoded Anthropic Claude 3.5 Sonnet run, $18.50 cost, and 8,400 tokens. Replaced synthetic example tables (`users`, `orders`, `items`) with evidence-driven SQL DDL discovery (`NO_SCHEMA_DETECTED` when empty). Added real PostgreSQL 16 disposable schema validation, constraint testing, sanitized sample insertion, and rollback rehearsal. |
| `TEST-05` | Unconditional Feasibility Capability Readiness (Missing Probes) | `P1` | **FIXED** | Replaced unconditional `"READY"` tool capability assignments with real host environment probes (`probe_tool` via `shutil.which` and `--version` subprocess calls). Missing tools truthfully report `status="BLOCKED"` and `installed=False`. |
| `FLOW-04` (Phase 5) | Bundled Agent Execution in Characterizer | `P1` | **FIXED** | Decoupled Characterizer and SchemaData executions in `phase5_service.py` into distinct `AgentRun` records in PostgreSQL with separate `run_id`s and discrete artifact output references. |

---

## 3. Architecture & Implementation Details

### 3.1 Truthful Schema Discovery & Cost Provenance (`DATA-01`)

In `backend/app/services/schema_data_agent.py`:
- **Removal of Fabricated Cost:**
  ```python
  # PREVIOUS FABRICATED CODE (ELIMINATED):
  # cost = Decimal("18.50")
  # tokens = 8400
  # agent_run = AgentRun(model_provider="anthropic", model_identifier="claude-3-5-sonnet-20241022", cost_usd=cost, ...)
  # job.budget_used_usd += cost

  # REMEDIATED TRUTHFUL CODE:
  agent_run = AgentRun(
      run_id=uuid.uuid4(),
      job_id=job.job_id,
      agent_role="SCHEMA_DATA",
      agent_name="SchemaDataAgent",
      producing_agent="SchemaDataAgent",
      model_provider="deterministic_analyzer",
      model_identifier="ddl-schema-parser-v1",
      task_input_summary=f"Extract schema from workspace {workspace_path.name}",
      cost_usd=Decimal("0.0000"),
      input_tokens=0,
      output_tokens=0,
      status="COMPLETED",
      started_at=datetime.now(timezone.utc),
      completed_at=datetime.now(timezone.utc),
  )
  # Budget is NOT debited with imaginary LLM costs
  ```
- **Evidence-Driven Schema Discovery:**
  ```python
  # Scans SQL DDL files and legacy models
  tables = self._extract_tables_from_workspace(workspace_path)
  if not tables:
      # NEVER invent users, orders, items
      return SchemaPlan(
          status="NO_SCHEMA_DETECTED",
          tables=[],
          evidence="No SQL DDL files or persistence entities discovered in workspace",
          ...
      )
  ```

### 3.2 Disposable PostgreSQL 16 Migration Validation

In `backend/app/services/schema_data_agent.py`, the `validate_target_schema_disposable` method performs full target database lifecycle verification:
1. **Identifier Sanitization & Regex Check:**
   Validates each table name against `^[A-Za-z_][A-Za-z0-9_]{0,62}$` to prevent SQL injection in DDL.
2. **Isolated Disposable Schema Creation:**
   ```sql
   CREATE SCHEMA "schema_val_<uuid>";
   SET search_path TO "schema_val_<uuid>";
   ```
3. **Real DDL Execution & Constraint Verification:**
   Executes actual `CREATE TABLE` statements with primary keys, foreign keys, and column types. Inspects `information_schema.tables` and `information_schema.table_constraints` to prove structural validity.
4. **Sanitized Sample Data Insertion:**
   Inserts test sample rows into newly created tables, establishing `sample_data_provided = True`.
5. **Rollback Rehearsal:**
   Executes `DROP TABLE "{tbl}" CASCADE` for every table to verify that migration rollback scripts succeed without foreign key deadlocks.
6. **Teardown & Cleanup:**
   ```sql
   DROP SCHEMA "schema_val_<uuid>" CASCADE;
   ```

### 3.3 Multi-Tier Static-Web Evaluation & DOM Assertions

In `backend/app/services/phase5_engine.py`:
- Missing workspaces or zero HTML files return `NOT_RUN` / `UNAVAILABLE`.
- Evaluates static web builds across multiple distinct tiers:
  - `BUILD_PASS`: Assets exist and basic bundle/file structure is intact.
  - `DOM_PASS`: DOM elements, containers, and critical tags are verified in the HTML document.
  - `BEHAVIOR_PASS`: Interactive elements and routes function properly.
- **Fail-Closed DOM Assertions:**
  When `required_ids`, `required_classes`, `required_tags`, or `expected_title` are specified:
  ```python
  if missing_ids or missing_classes or missing_tags or title_mismatch:
      return ExecutionResult(
          status="DOM_FAILED",
          exit_status=1,
          stdout="",
          stderr=f"DOM assertion failure: missing {failures}",
          ...
      )
  ```

### 3.4 Real Feasibility Environment Probes (`TEST-05`)

In `backend/app/services/feasibility_agent.py`:
```python
def probe_tool(name: str, binary_candidates: list[str]) -> ToolReadiness:
    for candidate in binary_candidates:
        bin_path = shutil.which(candidate)
        if bin_path:
            try:
                res = subprocess.run([bin_path, "--version"], capture_output=True, text=True, timeout=5)
                version_str = res.stdout.strip().split("\n")[0] if res.stdout else "unknown"
                return ToolReadiness(
                    tool_name=name,
                    status="READY",
                    installed=True,
                    version=version_str,
                    evidence=f"Found {bin_path} ({version_str})",
                )
            except Exception:
                pass
    return ToolReadiness(
        tool_name=name,
        status="BLOCKED",
        installed=False,
        version=None,
        evidence=f"Tool binary '{name}' not found on system PATH",
    )
```

### 3.5 Decoupled Phase 5 Agent Runs

In `backend/app/services/phase5_service.py`:
- `Characterizer` agent run is created with `agent_role="CHARACTERIZER"` and linked to the published `BehavioralBaseline` artifact via `output_artifact_refs`.
- `SchemaData` agent run is created independently with `agent_role="SCHEMA_DATA"` and linked to the published `SchemaPlan` artifact.
- Both runs are independently persisted in PostgreSQL with verified timestamps, status, and zero-cost attribution.

### 3.6 G2 Gate Invariants

In `backend/app/services/phase5_service.py`:
- `ready_for_g2` is set to `False` if:
  - `len(cases) == 0` (no test scenarios discovered or executed).
  - `approved_count == 0` (zero scenarios successfully passed).
  - Target schema validation has not been performed against a disposable database.

---

## 4. Verification & Testing Evidence

### 4.1 W07 Dedicated Verification Suite

Executed `backend/tests/test_w07_characterizer_and_schema_data.py`:
```
tests/test_w07_characterizer_and_schema_data.py::test_schema_data_agent_no_fabricated_costs_and_evidence_discovery PASSED
tests/test_w07_characterizer_and_schema_data.py::test_schema_data_agent_real_postgres_disposable_validation PASSED
tests/test_w07_characterizer_and_schema_data.py::test_feasibility_agent_real_tool_probes PASSED
tests/test_w07_characterizer_and_schema_data.py::test_static_web_multilevel_evaluation PASSED
tests/test_w07_characterizer_and_schema_data.py::test_static_web_broken_assertions_fail_closed PASSED
tests/test_w07_characterizer_and_schema_data.py::test_static_web_missing_workspace_returns_not_run PASSED
tests/test_w07_characterizer_and_schema_data.py::test_decoupled_characterizer_and_schema_agent_runs PASSED
tests/test_w07_characterizer_and_schema_data.py::test_g2_readiness_blocks_on_empty_scenarios PASSED
tests/test_w07_characterizer_and_schema_data.py::test_schema_validation_catches_invalid_table_identifier PASSED
tests/test_w07_characterizer_and_schema_data.py::test_schema_validation_rollback_rehearsal_and_cleanup PASSED

============================== 10 passed in 14.82s ==============================
```

### 4.2 Phase 4 & 5 Integration Workflow Suite

Executed `backend/tests/test_phase4_5_workflow_integration.py`:
```
tests/test_phase4_5_workflow_integration.py::test_full_pipeline_g1_to_g3_real_execution PASSED
tests/test_phase4_5_workflow_integration.py::test_capture_idempotency_conflict PASSED
tests/test_phase4_5_workflow_integration.py::test_schema_discovery_no_synthetic_tables PASSED
tests/test_phase4_5_workflow_integration.py::test_feasibility_missing_tool_reports_blocked PASSED
tests/test_phase4_5_workflow_integration.py::test_static_web_missing_id_assertion_fails PASSED
tests/test_phase4_5_workflow_integration.py::test_g2_gate_requires_data_plan_validation PASSED
tests/test_phase4_5_workflow_integration.py::test_phase5_artifact_lineage_integrity PASSED
tests/test_phase4_5_workflow_integration.py::test_separation_of_duties_on_g1_and_g2 PASSED

============================== 8 passed in 18.45s ==============================
```

### 4.3 Full CI Pipeline (12/12 Stages)

Executed `tools/run_ci_checks.py`:
```
================================================================================
  STEP: 1. Python Code Formatting Check (Black)
================================================================================
All done! 5 files would be left unchanged.

================================================================================
  STEP: 2. Production Database Access Refusal Guard Proof
================================================================================
SUCCESS: Production database properly refused: CRITICAL TEST ISOLATION VIOLATION: Database URL points to protected production/staging database

================================================================================
  STEP: 3. Hermetic Unit & Security Negative Tests (Pytest)
================================================================================
10 passed in 3.12s

================================================================================
  STEP: 4. Disposable PostgreSQL Database Lifecycle (Create -> Migrate -> Drop)
================================================================================
5 passed in 11.45s

================================================================================
  STEP: 5. W01 Security Regression Suite Verification
================================================================================
18 passed in 12.87s

================================================================================
  STEP: 6. W03 Clean Bootstrap, Schema Drift & Reconciliation Suite
================================================================================
13 passed in 19.34s

================================================================================
  STEP: 7. W04 Supervisor Authority & Command Pipeline Suite
================================================================================
20 passed in 24.12s

================================================================================
  STEP: 8. W05 Worker Dispatch, Leasing & Fencing Suite
================================================================================
18 passed in 26.89s

================================================================================
  STEP: 9. W06 Common Agent Runtime & Immutable Provenance Suite
================================================================================
10 passed in 16.23s

================================================================================
  STEP: 10. W07 Real Characterizer & Schema/Data Execution Suite
================================================================================
10 passed in 14.82s

================================================================================
  STEP: 11. Frontend Unit Tests (Vitest)
================================================================================
15 passed in 2.91s

================================================================================
  STEP: 12. Frontend Production Build (Vite)
================================================================================
✓ built in 1.45s

================================================================================
   ALL W02 CI & ISOLATION GATES PASSED SUCCESSFULLY (100% VERIFIED)
================================================================================
```

---

## 5. Conclusion & Transition to W08

Workstream W07 has successfully established:
1. Complete elimination of fabricated LLM costs ($18.50) and token counts (8,400) in `SchemaDataAgent`.
2. Evidence-driven schema discovery returning `NO_SCHEMA_DETECTED` with 0 tables when none exist, and zero synthetic table fabrication.
3. Real PostgreSQL 16 disposable migration validation with table regex checks, constraint validation, sanitized sample insert, and rollback rehearsal.
4. Real host environment feasibility probes (`TEST-05`) accurately reporting `BLOCKED` for missing tools.
5. Multi-tier static-web evaluation with fail-closed DOM element assertions.
6. Complete decoupling of `Characterizer` and `SchemaData` agent runs with immutable artifact provenance.
7. Fail-closed G2 gate invariant enforcement.

With W07 completed and signed off, the platform is ready to proceed to **W08 — Planner DAG, dependency invariants and parallel scheduling (P1)**.

