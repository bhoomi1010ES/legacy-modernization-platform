import psycopg2

conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/rebase")
cur = conn.cursor()

cur.execute("""
    SELECT conname, pg_get_constraintdef(c.oid)
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    WHERE t.relname IN ('modules', 'module_attempts', 'workflow_outbox', 'workflow_gates', 'jobs')
""")
for r in cur.fetchall():
    print(r)

conn.close()

