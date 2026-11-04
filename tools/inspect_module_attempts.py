import psycopg2

conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/rebase")
cur = conn.cursor()

cur.execute("SELECT status, count(*) FROM module_attempts GROUP BY status")
print("Module attempts by status:", cur.fetchall())

cur.execute("""
    SELECT attempt_id, module_id, status, started_at, completed_at
    FROM module_attempts
    WHERE status = 'RUNNING'
    LIMIT 30
""")
running_attempts = cur.fetchall()
print(f"RUNNING attempts count: {len(running_attempts)}")
for att in running_attempts[:5]:
    print(att)

conn.close()

