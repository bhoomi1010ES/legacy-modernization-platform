path = "docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if "### `FLOW-01`:" in line:
        start_idx = i
    elif start_idx is not None and line.strip() == "---":
        end_idx = i
        break

assert start_idx is not None and end_idx is not None, "FLOW-01 block not found"

new_flow01_lines = [
    "### `FLOW-01`: Serial Module Execution in Authoritative Supervisor Router\n",
    "- **Severity:** `P1`\n",
    "- **Workstream Target:** `W04` / `W05`\n",
    "- **Audit Sources:** Latest Oct 30 Audit §A.4, §E; `LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md` §7\n",
    "- **Source File Pointer:** `backend/app/services/supervisor_router.py` (lines 680–710), `backend/app/services/worker_dispatch_service.py`\n",
    "- **Verified Code:** Replaced serial single-element selection in `supervisor_router.py` with multi-module parallel metadata (`ready_modules`, `parallel_capacity`, `parallel_fanout_eligible`) and added `evaluate_parallel_actions`. Implemented atomic parallel task leasing with capacity limit in `WorkerDispatchService.claim_ready_tasks`.\n",
    "- **Reproduction Recipe:**\n",
    "  1. Create job with 5 independent modules in Wave 1.\n",
    "  2. Evaluate supervisor decision and parallel actions; verify all ready modules are discovered and multiple ready modules are claimed concurrently.\n",
    "- **Commit / Env:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` / `ENV-LOCAL-DEV-POSTGRES18`\n",
    "- **Test ID:** `backend/tests/test_w05_worker_dispatch.py::test_parallel_module_dispatch_flow01`\n",
    "- **Fix PR:** `PR-W05-PARALLEL-MODULE-FANOUT`\n",
    "- **Current Status:** `FIXED`\n",
    "- **Closure Decision:** `RESOLVED_IN_W05 (2026-10-30)`: Replaced single-element selection with parallel fan-out evaluation and multi-task claiming up to concurrency capacity. Monotonic lease generations and unique lease tokens issued per task. Verified by `test_w05_worker_dispatch.py::test_parallel_module_dispatch_flow01`.\n",
]

lines[start_idx:end_idx] = new_flow01_lines

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Updated REMEDIATION_EVIDENCE_LEDGER.md with FLOW-01 resolution successfully")
