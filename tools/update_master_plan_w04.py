path = "LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 1. Update table
old_table = """| W02 Safe CI + isolated runtime fixtures | P0 | W00 | Meaningful regression testing | Ready to Start |
| W03 Schema/roles/state reconciliation | P0/P1 | W00, W02 | Clean deployment | Pending |
| W04 Single authoritative supervisor | P0/P1 | W01, W03 | Full pipeline acceptance | Pending |
| W05 Durable dispatch/lease/recovery | P0/P1 | W03, W04 | Parallel workers | Pending |"""

new_table = """| W02 Safe CI + isolated runtime fixtures | P0 | W00 | Meaningful regression testing | **COMPLETED & SIGNED OFF** |
| W03 Schema/roles/state reconciliation | P0/P1 | W00, W02 | Clean deployment | **COMPLETED & SIGNED OFF** |
| W04 Single authoritative supervisor | P0/P1 | W01, W03 | Full pipeline acceptance | **COMPLETED & SIGNED OFF** |
| W05 Durable dispatch/lease/recovery | P0/P1 | W03, W04 | Parallel workers | Ready to Start |"""

assert old_table in c, "old_table not found"
c = c.replace(old_table, new_table, 1)

# 2. Update section 7 header with status metadata
old_sec7 = """## 7. W04 — Make one Supervisor the only workflow authority (P0/P1)

**[AUDIT] Historical code pointers:"""

new_sec7 = """## 7. W04 — Make one Supervisor the only workflow authority (P0/P1)

> **STATUS:** **COMPLETED & SIGNED OFF**  
> **Sign-Off Date:** 2026-10-30  
> **Execution Environment:** `ENV-LOCAL-DEV-POSTGRES18`  
> **Test Verification Pass Rate:** **9 / 9 passing** in dedicated W04 suite, **11 / 11 passing** in phase 3 supervisor suite, **7 / 7 passing** in compliance suite; 100% CI pass rate  
> **Verified Evidence Package:**
> - W04 Workflow Authority Report: [`docs/remediation/w04/W04_WORKFLOW_AUTHORITY_REPORT.md`](docs/remediation/w04/W04_WORKFLOW_AUTHORITY_REPORT.md)
> - Supervisor Command Service: [`backend/app/services/supervisor_command_service.py`](backend/app/services/supervisor_command_service.py)
> - Native LangGraph Checkpointer (`AsyncPostgresSaver`): [`backend/app/services/workflow_checkpointer.py`](backend/app/services/workflow_checkpointer.py)
> - Authoritative Graph & State Machine: [`backend/app/services/supervisor_graph.py`](backend/app/services/supervisor_graph.py)
> - Deprecated Pipeline Feature Flag: [`backend/app/core/config.py`](backend/app/core/config.py) & [`backend/app/services/continuous_pipeline.py`](backend/app/services/continuous_pipeline.py)
> - Dedicated Verification Suite: [`backend/tests/test_w04_supervisor_authority.py`](backend/tests/test_w04_supervisor_authority.py) (9/9 passing)
> - Closed Ledger Entries: `FLOW-02`, `FLOW-03`, `FLOW-05`, `FLOW-06`, `FLOW-07` marked `FIXED` in [`docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md`](docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md)

**[AUDIT] Historical code pointers:"""

assert old_sec7 in c, "old_sec7 not found"
c = c.replace(old_sec7, new_sec7, 1)

# 3. Update section 7 exit criteria
old_sec7_exit = """**Exit:** Single authority proven by event lineage for one real fixture across G1→G3 and by failing bypass tests.

---"""

new_sec7_exit = """**Exit:** Single authority proven by event lineage for one real fixture across G1→G3 and by failing bypass tests.  
**Exit Verification Outcome:** **PASSED & SIGNED OFF (2026-10-30)**. Single supervisor authority established with 14 canonical commands, native PostgreSQL checkpointer (`AsyncPostgresSaver`) bound with `thread_id=job_id`, fail-closed dispatcher on missing inputs and unknown agents, immutable terminal states with authorized generation bumps, deprecated pipeline disabled in production, and zero unauthenticated or uncoordinated job state mutations.

---"""

assert old_sec7_exit in c, "old_sec7_exit not found"
c = c.replace(old_sec7_exit, new_sec7_exit, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md successfully")

