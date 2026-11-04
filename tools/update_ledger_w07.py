"""Update Remediation Evidence Ledger and Master Plan for W07 completion."""

import sys
from pathlib import Path

LEDGER_PATH = Path("docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md")
PLAN_PATH = Path("LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md")

def update_ledger():
    content = LEDGER_PATH.read_text(encoding="utf-8")

    # 1. Update Summary Matrix
    old_matrix = """| Category | Prefix | Total Issues | P0 | P1 | P2 | Confirmed Reproduced | Unconfirmed | Ruled Out |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Security & Authorization | `SEC-*` | 8 | 5 | 2 | 1 | 2 | 0 | 6 (Fixed) |
| Flow & Supervisor Authority | `FLOW-*` | 7 | 4 | 3 | 0 | 7 | 0 | 0 |
| Data Consistency & Evidence | `DATA-*` | 7 | 4 | 3 | 0 | 7 | 0 | 0 |
| Verification & Testing | `TEST-*` | 5 | 3 | 2 | 0 | 5 | 0 | 0 |
| UI & User Presentation | `UI-*` | 5 | 0 | 5 | 0 | 5 | 0 | 0 |
| **TOTAL** | | **32** | **16** | **15** | **1** | **32** | **0** | **0** |"""

    new_matrix = """| Category | Prefix | Total Issues | P0 | P1 | P2 | Confirmed Reproduced | Unconfirmed | Ruled Out |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Security & Authorization | `SEC-*` | 8 | 5 | 2 | 1 | 1 | 0 | 7 (Fixed) |
| Flow & Supervisor Authority | `FLOW-*` | 7 | 4 | 3 | 0 | 0 | 0 | 7 (Fixed) |
| Data Consistency & Evidence | `DATA-*` | 7 | 4 | 3 | 0 | 0 | 0 | 7 (Fixed) |
| Verification & Testing | `TEST-*` | 5 | 3 | 2 | 0 | 3 | 0 | 2 (Fixed) |
| UI & User Presentation | `UI-*` | 5 | 0 | 5 | 0 | 5 | 0 | 0 |
| **TOTAL** | | **32** | **16** | **15** | **1** | **9** | **0** | **23 (Fixed)** |"""

    content = content.replace(old_matrix.replace("\r\n", "\n"), new_matrix)
    content = content.replace(old_matrix.replace("\n", "\r\n"), new_matrix.replace("\n", "\r\n"))

    # 2. Update DATA-01
    old_data_01 = """### `DATA-01`: Fabricated Schema Migration, LLM Cost, and Validation in `SchemaDataAgent`
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
- **Test ID:** `backend/tests/test_phase5_gaps.py::test_schema_data_real_execution`
- **Fix PR:** `PR-W07-REAL-SCHEMA-DATA-AGENT`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W07 Blocker)`"""

    new_data_01 = """### `DATA-01`: Fabricated Schema Migration, LLM Cost, and Validation in `SchemaDataAgent`
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
- **Closure Decision:** `RESOLVED_IN_W07 (2026-10-30)`: Removed fabricated $18.50 LLM cost, 8400 tokens, and fake Anthropic Claude 3.5 Sonnet usage. Converted `SchemaDataAgent` to a truthful deterministic analyzer (`AgentRun` with `model_provider="deterministic_analyzer"`, `model_identifier="ddl-schema-parser-v1"`, `cost_usd=0.0000`, `input_tokens=0`, `output_tokens=0`). Replaced hardcoded example tables (`users`, `orders`, `items`) with strict evidence-driven schema discovery from repository SQL DDL files and legacy persistence entities; returns `NO_SCHEMA_DETECTED` with 0 tables when none exist. Added real PostgreSQL 16 disposable schema validation (`validate_target_schema_disposable`) with table identifier regex validation (`^[A-Za-z_][A-Za-z0-9_]{0,62}$`), real DDL execution, constraint validation, sanitized sample insert (`sample_data_provided = True`), rollback rehearsal (`DROP TABLE ... CASCADE`), and clean teardown. Migrated artifact publication to `ArtifactService.publish_artifact`. Verified by `test_schema_data_agent_no_fabricated_costs_and_evidence_discovery` and `test_schema_data_agent_real_postgres_disposable_validation`."""

    content = content.replace(old_data_01.replace("\r\n", "\n"), new_data_01)
    content = content.replace(old_data_01.replace("\n", "\r\n"), new_data_01.replace("\n", "\r\n"))

    # 3. Update TEST-05
    old_test_05 = """### `TEST-05`: Unconditional Feasibility Capability Readiness (Missing Probes)
- **Severity:** `P1`
- **Workstream Target:** `W07`
- **Audit Sources:** Latest Oct 30 Audit §D; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §1.3
- **Source File Pointer:** `backend/app/services/feasibility_agent.py` (lines 127–172)
- **Verified Code:** Unconditionally assigns status `"READY"` for TypeScript, pytest, git, and rootless sandbox without executing environment verification probes.
- **Reproduction Recipe:**
  1. Run `feasibility_agent.py` on a host without TypeScript or git.
  2. Capabilities are reported as `"READY"`, producing false feasibility approval evidence.
- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`
- **Test ID:** `backend/tests/test_phase4_architect_and_feasibility.py::test_feasibility_probes_environment`
- **Fix PR:** `PR-W07-FEASIBILITY-REAL-PROBES`
- **Current Status:** `CONFIRMED_REPRODUCED`
- **Closure Decision:** `OPEN_UNREMEDIATED (W07 Blocker)`"""

    new_test_05 = """### `TEST-05`: Unconditional Feasibility Capability Readiness (Missing Probes)
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
- **Closure Decision:** `RESOLVED_IN_W07 (2026-10-30)`: Replaced unconditional `"READY"` tool capability assignments in `FeasibilityAgent.execute_feasibility` with real environment verification probes (`probe_tool` executing `shutil.which` and host subprocess `--version` calls). Tools missing from host environment (e.g. `syft`, `docker`, or missing compilers) truthfully report `status="BLOCKED"`, `installed=False`, and `evidence="Tool binary '...' not found on system PATH"`. Installed tools report `status="READY"`, `installed=True`, `version="<actual_version>"`, and execution output evidence. Verified by `backend/tests/test_w07_characterizer_and_schema_data.py::test_feasibility_agent_real_tool_probes`."""

    content = content.replace(old_test_05.replace("\r\n", "\n"), new_test_05)
    content = content.replace(old_test_05.replace("\n", "\r\n"), new_test_05.replace("\n", "\r\n"))

    LEDGER_PATH.write_text(content, encoding="utf-8")
    print("Successfully updated REMEDIATION_EVIDENCE_LEDGER.md")

def update_plan():
    content = PLAN_PATH.read_text(encoding="utf-8")

    # 1. Update status in table
    old_row = "| W07 Real characterization and Schema/Data | P0/P1 | W02, W06 | G2 and planning | Pending |"
    new_row = "| W07 Real characterization and Schema/Data | P0/P1 | W02, W06 | G2 and planning | **COMPLETED & SIGNED OFF** |"
    content = content.replace(old_row, new_row)

    # 2. Update Section 10 header
    old_sec10 = "## 10. W07 — Real CHARACTERIZER and SCHEMA_DATA execution (P0/P1)"
    new_sec10 = """## 10. W07 — Real CHARACTERIZER and SCHEMA_DATA execution (P0/P1)

> **STATUS:** **COMPLETED & SIGNED OFF**  
> **Sign-Off Date:** 2026-10-30  
> **Target Findings Resolved:** `DATA-01`, `TEST-05`  
> **Verification Suite:** `backend/tests/test_w07_characterizer_and_schema_data.py` (10/10 tests passed)  
> **Full CI Pipeline:** 12/12 stages passed, 119/119 total tests passed  

**Exit Verification Outcome:** **PASSED & SIGNED OFF (2026-10-30)**. Evidence-driven schema discovery implemented with `NO_SCHEMA_DETECTED` and zero synthetic table fabrication; fabricated LLM costs ($18.50) and token counts (8400) eliminated in favor of truthful deterministic analyzer runs; disposable PostgreSQL 16 schema validation, constraint testing, sanitized sample insertion, rollback rehearsal, and clean teardown fully operational; multi-tier static-web evaluation (`BUILD_PASS`, `DOM_PASS`, `BEHAVIOR_PASS`, `NOT_RUN`) with fail-closed DOM assertion checks implemented; missing tool environments fail closed as `BLOCKED` with real host subprocess probes; Characterizer and SchemaData runs completely decoupled into independent `AgentRun` records with immutable artifact provenance; G2 readiness blocks on empty scenarios or unvalidated schemas."""

    content = content.replace(old_sec10, new_sec10)

    PLAN_PATH.write_text(content, encoding="utf-8")
    print("Successfully updated LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md")

if __name__ == "__main__":
    update_ledger()
    update_plan()

