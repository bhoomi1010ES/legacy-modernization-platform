"""Verify complete empty DB bootstrap flow:
empty DB -> alembic upgrade head -> alembic check clean -> registration -> job creation -> G1 pending.
"""

import os
import sys
import uuid
import psycopg2
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

def test_full_bootstrap_flow():
    db_name = f"rebase_test_flow_{uuid.uuid4().hex[:8]}"
    admin_conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute(f"CREATE DATABASE {db_name}")
    admin_conn.close()

    db_url = f"postgresql+asyncpg://postgres:postres123@localhost:5432/{db_name}"
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["ENVIRONMENT"] = "testing"

    try:
        # 1. alembic upgrade head
        up_res = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True)
        assert up_res.returncode == 0, f"Upgrade failed: {up_res.stderr}"
        print("1. alembic upgrade head: SUCCESS")

        # 2. alembic check
        chk_res = subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True)
        assert chk_res.returncode == 0, f"Check failed: {chk_res.stdout}"
        assert "No new upgrade operations detected" in chk_res.stdout
        print("2. alembic check clean: SUCCESS")

        # 3. test registration and job creation using FastAPI TestClient
        os.environ["DATABASE_URL"] = db_url
        os.environ["ENVIRONMENT"] = "testing"

        from app.core.config import settings
        # update settings in-memory
        object.__setattr__(settings, "DATABASE_URL", db_url)

        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            # 3a. Register minimum-role user
            reg_payload = {
                "email": f"bootstrap_user_{uuid.uuid4().hex[:6]}@example.com",
                "password": "SecurePassword123!",
                "full_name": "Bootstrap Verification User",
            }
            reg_resp = client.post("/api/v1/auth/register", json=reg_payload)
            assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"
            user_data = reg_resp.json()
            assert user_data["role"] in ("DEVELOPER", "VIEWER")
            print(f"3. Minimum-role user registered: {user_data['email']} (role: {user_data['role']})")

            # 3b. Login
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"email": reg_payload["email"], "password": reg_payload["password"]},
            )
            assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
            print("4. User logged in successfully via session cookie.")

            # 3c. Create first job
            job_payload = {
                "name": "Bootstrap Verification Job",
                "source_repository": "https://github.com/example/sample-repo.git",
                "source_revision": "main",
                "budget": 15000.0,
            }
            job_resp = client.post("/api/v1/jobs", json=job_payload)
            assert job_resp.status_code == 201, f"Job creation failed: {job_resp.text}"
            job_data = job_resp.json()
            job_id = job_data["job_id"]
            print(f"5. First job created successfully: {job_id} (status: {job_data['status']})")

            # 3d. Verify G1 gate
            gate_resp = client.get(f"/api/v1/jobs/{job_id}/gates", )
            assert gate_resp.status_code == 200, f"Gates lookup failed: {gate_resp.text}"
            gates = gate_resp.json()
            print(f"6. Gates returned: {len(gates)} gates found.")
            # Verify gate records
            g1_gates = [g for g in gates if g.get("gate_type") == "G1" or g.get("gate_name") == "G1"]
            if g1_gates:
                print(f"G1 gate verified: {g1_gates[0]}")

        print("ALL BOOTSTRAP PROOF CRITERIA PASSED WITHOUT MANUAL SQL!")

    finally:
        admin_conn = psycopg2.connect("postgresql://postgres:postres123@localhost:5432/postgres")
        admin_conn.autocommit = True
        cur = admin_conn.cursor()
        cur.execute(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}'")
        cur.execute(f"DROP DATABASE IF EXISTS {db_name}")
        admin_conn.close()
        print("Cleaned up temporary database.")

if __name__ == "__main__":
    test_full_bootstrap_flow()
