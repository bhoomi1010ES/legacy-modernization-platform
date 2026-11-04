import psycopg2

conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/rebase")
cur = conn.cursor()

# 1. Modules VERIFIED without verified attempt
cur.execute("""
    SELECT count(*) FROM modules m
    WHERE m.status = 'VERIFIED'
      AND NOT EXISTS (
        SELECT 1 FROM module_attempts a
        WHERE a.module_id = m.module_id AND a.status = 'VERIFIED'
      )
""")
verified_no_attempt = cur.fetchone()[0]
print(f"1. Modules VERIFIED without verified attempt: {verified_no_attempt}")

# 2. RUNNING module attempts or modules with expired leases
cur.execute("""
    SELECT count(*) FROM module_attempts a
    JOIN modules m ON a.module_id = m.module_id
    WHERE a.status = 'RUNNING' AND m.lease_expires_at < now()
""")
expired_running_attempts = cur.fetchone()[0]
print(f"2. RUNNING module attempts with expired lease: {expired_running_attempts}")

cur.execute("""
    SELECT count(*) FROM modules
    WHERE status = 'RUNNING' AND lease_expires_at < now()
""")
expired_running_modules = cur.fetchone()[0]
print(f"2b. RUNNING modules with expired lease: {expired_running_modules}")

# 3. Outbox counts
cur.execute("SELECT status, count(*) FROM workflow_outbox GROUP BY status")
outbox_counts = cur.fetchall()
print(f"3. Workflow outbox counts by status: {outbox_counts}")

# 4. Gate / Job disagreements
cur.execute("""
    SELECT count(*) FROM workflow_gates g
    JOIN jobs j ON g.job_id = j.job_id
    WHERE g.status = 'PENDING'
      AND j.status NOT IN ('AWAITING_GATE', 'AWAITING_APPROVAL', 'GATE_PENDING')
""")
gate_disagreements = cur.fetchone()[0]
print(f"4. PENDING gates on non-awaiting jobs: {gate_disagreements}")

# 5. Stale orchestration leases on active jobs
cur.execute("""
    SELECT count(*) FROM jobs
    WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')
      AND orchestration_lease_expires_at < now()
""")
stale_job_leases = cur.fetchone()[0]
print(f"5. Active jobs with expired orchestration lease: {stale_job_leases}")

conn.close()

