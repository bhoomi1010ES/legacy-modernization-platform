import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.database import AsyncSessionLocal
from sqlalchemy import text
from app.models.job import Job
from app.models.module import Module, ModuleAttempt

JOB_ID = "eb2bbaa9-90ee-4e9d-b340-5e025594126c"
MODULE_NAME = "comp_app-models_681831"

async def inspect():
    async with AsyncSessionLocal() as db:
        print("=== 1. JOB STATUS ===")
        job = await db.get(Job, JOB_ID)
        if job:
            print(f"Job: status={job.status}, active_node={job.active_node}, last_transition={job.last_transition}")
            print(f"  blocking_reason={job.blocking_reason}, terminal_reason={job.terminal_reason}")
            print(f"  budget_used_usd={job.budget_used_usd}, budget_limit_usd={job.budget_limit_usd}")
            print(f"  workflow_retry_count={job.workflow_retry_count}")

        print("\n=== 2. TARGET MODULE STATUS ===")
        mod_res = await db.execute(text(f"SELECT * FROM modules WHERE job_id = '{JOB_ID}' AND name = '{MODULE_NAME}'"))
        mod_row = mod_res.fetchone()
        if mod_row:
            mod_dict = dict(mod_row._mapping)
            print("Module:", mod_dict)
            mod_id = mod_dict['module_id']

            print("\n=== 3. LATEST ATTEMPTS FOR MODULE ===")
            att_res = await db.execute(text(f"SELECT * FROM module_attempts WHERE module_id = '{mod_id}' ORDER BY attempt_number DESC LIMIT 3"))
            attempts = att_res.fetchall()
            for att in attempts:
                att_d = dict(att._mapping)
                print(f"Attempt #{att_d.get('attempt_number')} (id={att_d.get('attempt_id')}):")
                print(f"  status={att_d.get('status')}, failure_category={att_d.get('failure_category')}")
                print(f"  blocking_reason={att_d.get('blocking_reason')}")
                print(f"  traceback={att_d.get('traceback')}")
                print(f"  error_detail={att_d.get('error_detail')}")
                print(f"  created_at={att_d.get('created_at')}")

            # Check agent_runs for the latest attempt
            if attempts:
                for att in attempts:
                    att_d = dict(att._mapping)
                    agent_run_id = att_d.get('agent_run_id')
                    print(f"\nAttempt #{att_d.get('attempt_number')} (id={att_d.get('attempt_id')}, agent_run_id={agent_run_id}, status={att_d.get('status')}, failure_reason={att_d.get('failure_reason')}):")
                    if agent_run_id:
                        run_res = await db.execute(text(f"SELECT * FROM agent_runs WHERE run_id = '{agent_run_id}'"))
                        run_row = run_res.fetchone()
                        if run_row:
                            r_d = dict(run_row._mapping)
                            print(f"  AgentRun status={r_d.get('status')}, input_tokens={r_d.get('input_tokens')}, output_tokens={r_d.get('output_tokens')}, cost={r_d.get('cost_usd')}")
                            print(f"  error_message={r_d.get('error_message')}")
                            trace = r_d.get('trace_payload') or {}
                            print(f"  trace_action={trace.get('action')}, finish_reason={trace.get('provider_metadata', {}).get('finish_reason')}")
                            print(f"  provider_metadata={trace.get('provider_metadata')}")
                            # Check if output_payload exists
                            op = r_d.get('output_payload')
                            if op:
                                print(f"  output_payload keys: {list(op.keys()) if isinstance(op, dict) else type(op)}")
                                if isinstance(op, dict) and 'content' in op:
                                    content_str = str(op['content'])
                                    print(f"  content length: {len(content_str)}, end of content: {repr(content_str[-200:])}")

        print("\n=== 4. TABLES & TASKS ===")
        tables = (await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))).fetchall()
        print("Tables in DB:", [t[0] for t in tables if any(k in t[0] for k in ('task', 'lease', 'worker', 'queue', 'job', 'module'))])
        
        # Check jobs lease columns
        job_lease = await db.execute(text(f"SELECT job_id, orchestration_owner, orchestration_lease_expires_at, orchestration_generation FROM jobs WHERE job_id = '{JOB_ID}'"))
        print("Job lease:", job_lease.fetchone())

        # Check module lease columns
        mod_lease = await db.execute(text(f"SELECT module_id, name, wave_number, status, lease_owner, lease_expires_at FROM modules WHERE job_id = '{JOB_ID}' AND name = '{MODULE_NAME}'"))
        print("Module lease:", mod_lease.fetchone())

        print("\n=== 5. CHECKPOINTS ===")
        try:
            cp_res = await db.execute(text(f"SELECT checkpoint_id, sequence, checkpoint_kind, node_name, correlation_id, created_at FROM workflow_checkpoints WHERE job_id = '{JOB_ID}' ORDER BY sequence DESC LIMIT 5"))
            for cp in cp_res.fetchall():
                print("Checkpoint:", cp)
        except Exception as e:
            print("Checkpoints query error:", e)

        print("\n=== 6. ALL 14 MODULES ===")
        all_mods = await db.execute(text(f"SELECT module_id, name, wave_number, status, retry_count FROM modules WHERE job_id = '{JOB_ID}' ORDER BY wave_number, name"))
        for m in all_mods.fetchall():
            print(f"Wave {m[2]}: {m[1]} ({m[0]}) -> status={m[3]}, retries={m[4]}")

if __name__ == '__main__':
    asyncio.run(inspect())
