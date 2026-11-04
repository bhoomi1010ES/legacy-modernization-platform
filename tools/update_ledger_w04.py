path = r"docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# FLOW-02
old_flow02 = '''### `FLOW-02`: Competing Orchestration Engines and Deprecated Bypass Routes
- **Severity:** `P0`
- **Workstream Target:** `W04`
- **Audit Sources:** Latest Oct 30 Audit §B, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7
- **Source File Pointer:** `backend/app/services/continuous_pipeline.py` (lines 20–80), `backend/app/services/supervisor_graph.py` (lines 384–395)
- **Verified Code:** `ContinuousPipelineService` is labeled "deprecated" but continues to be invoked by the supervisor graph for characterization, and contains direct status-changing methods.
- **Reproduction Recipe:**
  1. Inspect `supervisor_graph.py` node `characterization`.
  2. Observe delegate call to `ContinuousPipelineService._run_characterization_stage` instead of canonical agent runner.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase3_authoritative_compliance.py::test_single_supervisor_authority`
- **Fix PR:** `PR-W04-DEPRECATED-PIPELINE-REMOVAL`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W04 Blocker)`'''

new_flow02 = '''### `FLOW-02`: Competing Orchestration Engines and Deprecated Bypass Routes
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
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Disabled direct `ContinuousPipelineService` invocation in production behind `ENABLE_LEGACY_CONTINUOUS_PIPELINE` feature flag. Replaced all characterization delegation in `supervisor_graph.py` with direct `capture` call. Replaced API calls in `phase6.py` and `phase7.py` with authoritative supervisor drives. Verified by `test_w04_supervisor_authority.py::test_continuous_pipeline_disabled_in_production_flow02`.''''

assert old_flow02 in c, "old_flow02 not found"
c = c.replace(old_flow02, new_flow02, 1)

# FLOW-03
old_flow03 = '''### `FLOW-03`: Autonomous Continuation Failure (Graph Premature Exit on Wait)
- **Severity:** `P1`
- **Workstream Target:** `W04`
- **Audit Sources:** Latest Oct 30 Audit §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7
- **Source File Pointer:** `backend/app/services/supervisor_graph.py` (lines 620–635, lines 755–758)
- **Verified Code:** `handle_wait` and `pause_for_human` route directly to `END`, terminating graph execution; recovery depends entirely on external background loops or restart hooks.
- **Reproduction Recipe:**
  1. Advance job to a pending gate or wait condition.
  2. Graph completes invocation and exits without persisting thread pause state.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase3_supervisor.py::test_durable_graph_interruption`
- **Fix PR:** `PR-W04-DURABLE-GRAPH-CONTINUATION`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W04 Blocker)`'''

new_flow03 = '''### `FLOW-03`: Autonomous Continuation Failure (Graph Premature Exit on Wait)
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
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Rewrote `node_handle_escalation` to record `WORKFLOW_ESCALATED` audit events and set blocking reasons without auto-failing jobs. Integrated `AsyncPostgresSaver` with durable interrupt at `pause_for_human` allowing resumption on the identical thread upon gate approval. Verified by `test_w04_supervisor_authority.py::test_escalation_does_not_auto_fail_flow03`.''''

assert old_flow03 in c, "old_flow03 not found"
c = c.replace(old_flow03, new_flow03, 1)

# FLOW-05
old_flow05 = '''### `FLOW-05`: Absence of Native LangGraph Postgres Checkpointer
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
- **Test ID:** `backend/tests/test_phase3_supervisor.py::test_langgraph_postgres_checkpointer`
- **Fix PR:** `PR-W04-LANGGRAPH-CHECKPOINTER`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W04 Blocker)`'''

new_flow05 = '''### `FLOW-05`: Absence of Native LangGraph Postgres Checkpointer
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
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Implemented `AsyncPostgresSaver` subclassing LangGraph's native `BaseCheckpointSaver`. Bound checkpoints to PostgreSQL `workflow_checkpoints` table with `thread_id=job_id` and durable interrupt before `pause_for_human`. Verified by `test_w04_supervisor_authority.py::test_langgraph_postgres_checkpointer_flow05`.''''

assert old_flow05 in c, "old_flow05 not found"
c = c.replace(old_flow05, new_flow05, 1)

# FLOW-06
old_flow06 = '''### `FLOW-06`: Out-of-Spec Recovery Directly Mutates Terminal `FAILED` Jobs to `CONVERTING`
- **Severity:** `P1`
- **Workstream Target:** `W04` / `W05`
- **Audit Sources:** Latest Oct 30 Audit §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7
- **Source File Pointer:** `backend/app/services/supervisor_service.py` (lines 1630–1660)
- **Verified Code:** `recover_failed_phase6_job` mutates `jobs.status` from terminal `FAILED` back to `CONVERTING` without supervisor command or audit lineage.
- **Reproduction Recipe:**
  1. Job enters terminal `FAILED`.
  2. Invoke recovery helper. Job status is forcibly changed to `CONVERTING`, violating terminal state invariants.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase3_supervisor.py::test_terminal_failed_immutability`
- **Fix PR:** `PR-W04-TERMINAL-STATE-RECOVERY`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W04 Blocker)`'''

new_flow06 = '''### `FLOW-06`: Out-of-Spec Recovery Directly Mutates Terminal `FAILED` Jobs to `CONVERTING`
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
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Enforced terminal `FAILED` immutability in `JobStateMachine` and `SupervisorCommandService`. Standard commands are rejected on `FAILED` jobs; only an authorized `RetryFailedJobCommand` by `ADMIN` with minimum 10-character rationale can create a new recovery generation (`orchestration_generation += 1`) with audit trail. Verified by `test_w04_supervisor_authority.py::test_terminal_failed_immutability_and_authorized_recovery_flow06`.''''

assert old_flow06 in c, "old_flow06 not found"
c = c.replace(old_flow06, new_flow06, 1)

# FLOW-07
old_flow07 = '''### `FLOW-07`: Fall-Through to `SUCCESS` on Unknown Agent or Missing Inputs
- **Severity:** `P0`
- **Workstream Target:** `W04`
- **Audit Sources:** Latest Oct 30 Audit §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.4
- **Source File Pointer:** `backend/app/services/supervisor_graph.py` (lines 340–420)
- **Verified Code:** Nodes for Architect / Feasibility return `SUCCESS` even when legacy inputs are missing, and unmapped agent branches default to `SUCCESS`.
- **Reproduction Recipe:**
  1. Pass an unmapped agent identifier to the dispatcher node.
  2. Node returns `status: SUCCESS` rather than failing closed.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase3_supervisor.py::test_unknown_agent_fails_closed`
- **Fix PR:** `PR-W04-FAIL-CLOSED-DISPATCH`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W04 Blocker)`'''

new_flow07 = '''### `FLOW-07`: Fall-Through to `SUCCESS` on Unknown Agent or Missing Inputs
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
- **Closure Decision:** `RESOLVED_IN_W04 (2026-10-30)`: Hardened `node_execute_agent` to validate prerequisite models for Architect and Feasibility and reject unmapped agent identifiers with `execution_verdict="ESCALATE"` and `UNKNOWN_AGENT_ESCALATION` audit events. Verified by `test_w04_supervisor_authority.py::test_unknown_agent_fails_closed_flow07`.''''

assert old_flow07 in c, "old_flow07 not found"
c = c.replace(old_flow07, new_flow07, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated REMEDIATION_EVIDENCE_LEDGER.md with W04 fixes successfully")

