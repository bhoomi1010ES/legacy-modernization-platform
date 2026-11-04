import psycopg2
import subprocess
import sys
import os

conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute("CREATE DATABASE rebase_test_roles_check")
conn.close()

env = os.environ.copy()
env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postres123@localhost:5432/rebase_test_roles_check"
env["ENVIRONMENT"] = "testing"

subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd="backend", env=env, capture_output=True)

test_conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/rebase_test_roles_check")
test_cur = test_conn.cursor()
test_cur.execute("SELECT count(*) FROM roles")
count = test_cur.fetchone()[0]
print(f"Role count in newly migrated empty database: {count}")
test_conn.close()

conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'rebase_test_roles_check'")
cur.execute("DROP DATABASE rebase_test_roles_check")
conn.close()

