import psycopg2
import os
import subprocess
import sys

def main():
    conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE DATABASE rebase_test_alembic_probe")
    conn.close()

    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+asyncpg://postgres:postres123@localhost:5432/rebase_test_alembic_probe"
    env["ENVIRONMENT"] = "testing"

    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd="backend",
        env=env,
        capture_output=True,
        text=True,
    )
    print("ALEMBIC UPGRADE STDOUT:", res.stdout)
    print("ALEMBIC UPGRADE STDERR:", res.stderr)
    print("Return code:", res.returncode)

    res_check = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd="backend",
        env=env,
        capture_output=True,
        text=True,
    )
    print("ALEMBIC CHECK STDOUT:", res_check.stdout)
    print("ALEMBIC CHECK STDERR:", res_check.stderr)
    print("Check Return code:", res_check.returncode)

    conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'rebase_test_alembic_probe'")
    cur.execute("DROP DATABASE rebase_test_alembic_probe")
    conn.close()
    print("Cleaned up successfully.")

if __name__ == "__main__":
    main()
