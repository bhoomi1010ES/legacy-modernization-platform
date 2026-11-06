import asyncpg
import asyncio
import json
import uuid

async def report():
    conn = await asyncpg.connect("postgresql://postgres:postres123@127.0.0.1:5432/rebase")
    job_id = uuid.UUID("26b905d7-0013-4dd2-84ec-39d8809d280b")
    
    # 1. Job Info
    job = await conn.fetchrow("SELECT * FROM jobs WHERE job_id = $1", job_id)
    print("==================================================")
    print("               JOB OVERVIEW                      ")
    print("==================================================")
    print(f"Job ID: {job['job_id']}")
    print(f"Name: {job['name']}")
    print(f"Source Repo: {job['source_repository']} ({job['source_revision']})")
    print(f"Source Stack: {job['source_stack']}")
    print(f"Target Stack: {job['target_stack']}")
    print(f"Platform Status: {job['status']}")
    print(f"Workflow Phase: {job['workflow_phase']}")
    print(f"Active Node: {job['active_node']}")
    print(f"Blocking Reason: {job['blocking_reason']}")
    print(f"Budget Spend: ${job['budget_used_usd']} / ${job['budget_limit_usd']}")
    print(f"Max Repair Attempts: {job['max_repair_attempts']}")

    # 2. Gate Decisions
    print("\n==================================================")
    print("              GATE DECISIONS (G1 - G4)            ")
    print("==================================================")
    gates = await conn.fetch("SELECT gate_type, decision, rationale, decided_at, reviewer_user_id FROM gate_decisions WHERE job_id = $1 ORDER BY decided_at", job_id)
    for g in gates:
        print(f"Gate {g['gate_type']}: {g['decision']} | Reviewer: {g['reviewer_user_id']} | Decided: {g['decided_at']}")
        print(f"   Rationale: {g['rationale']}")

    # 3. Agent Runs
    print("\n==================================================")
    print("                 AGENT RUNS                       ")
    print("==================================================")
    runs = await conn.fetch("SELECT run_id, agent_name, task_id, status, started_at, completed_at, error_message FROM agent_runs WHERE job_id = $1 ORDER BY started_at", job_id)
    for r in runs:
        print(f"Agent: {r['agent_name']:<25} | Status: {r['status']:<10} | Started: {r['started_at']} | Completed: {r['completed_at']}")
        if r['error_message']:
            print(f"   Error: {r['error_message']}")

    # 4. Modules
    print("\n==================================================")
    print("          MODULE EXECUTION & REPAIR BOARD         ")
    print("==================================================")
    modules = await conn.fetch("SELECT module_id, name, status, wave_number, dependency_module_ids FROM modules WHERE job_id = $1 ORDER BY wave_number, name", job_id)
    print(f"Total Modules: {len(modules)}")
    for m in modules:
        print(f"\nModule: {m['name']} (Wave {m['wave_number']})")
        print(f"   ID: {m['module_id']}")
        print(f"   Status: {m['status']}")
        print(f"   Dependencies: {m['dependency_module_ids']}")
        attempts = await conn.fetch("SELECT attempt_number, status, failure_reason, started_at FROM module_attempts WHERE module_id = $1 ORDER BY attempt_number", m["module_id"])
        print(f"   Attempts Recorded ({len(attempts)}):")
        for a in attempts:
            print(f"     - Attempt #{a['attempt_number']}: {a['status']} (Started: {a['started_at']}) | Reason: {a['failure_reason']}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(report())
