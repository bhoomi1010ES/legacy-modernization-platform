import psycopg2
import os
import subprocess
import sys
import uuid

def test_empty_db_bootstrap():
    db_name = f"rebase_test_boot_{uuid.uuid4().hex[:8]}"
    admin_conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute(f"CREATE DATABASE {db_name}")
    admin_conn.close()

    env = os.environ.copy()
    env["DATABASE_URL"] = f"postgresql+asyncpg://postgres:postres123@localhost:5432/{db_name}"
    env["ENVIRONMENT"] = "testing"

    try:
        # Step 1: alembic upgrade head
        up_res = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd="backend", env=env, capture_output=True, text=True)
        print("ALEMBIC UPGRADE RETURN CODE:", up_res.returncode)
        if up_res.returncode != 0:
            print("UPGRADE STDOUT:", up_res.stdout)
            print("UPGRADE STDERR:", up_res.stderr)
            raise RuntimeError("Upgrade failed")

        # Step 2: alembic check
        check_res = subprocess.run([sys.executable, "-m", "alembic", "check"], cwd="backend", env=env, capture_output=True, text=True)
        print("ALEMBIC CHECK RETURN CODE:", check_res.returncode)
        print("CHECK STDOUT:\n", check_res.stdout)
        print("CHECK STDERR:\n", check_res.stderr)

        # Step 3: verify roles seeded
        test_conn = psycopg2.connect(f"postgresql://postgres:postres123@localhost:5432/{db_name}")
        test_cur = test_conn.cursor()
        test_cur.execute("SELECT role_id, name FROM roles ORDER BY role_id")
        roles = test_cur.fetchall()
        print("SEEDED ROLES IN EMPTY DB:", roles)
        test_conn.close()
    finally:
        # Step 4: clean up
        admin_conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
        admin_conn.autocommit = True
        cur = admin_conn.cursor()
        cur.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}'")
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
        # also clean up old rebase_test_check_clean
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'rebase_test_check_clean'")
        cur.execute("DROP DATABASE IF EXISTS rebase_test_check_clean")
        admin_conn.close()
        print("Cleaned up database successfully.")

if __name__ == "__main__":
    test_empty_db_bootstrap()
