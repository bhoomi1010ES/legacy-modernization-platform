from pathlib import Path

test_file = Path("backend/tests/test_w03_schema_and_reconciliation.py")
content = test_file.read_text(encoding="utf-8")

flow_test = '''

# ==============================================================================
# 5. Full Bootstrap & Registration Flow Proof (Without Manual SQL)
# ==============================================================================

@pytest.mark.db_integration
def test_empty_db_bootstrap_to_first_job_flow():
    """Proof: empty DB -> upgrade head -> check clean -> register -> login -> create job without manual SQL."""
    manager = DisposableDatabaseManager()
    db_name = manager.generate_database_name()
    manager.create_database(db_name)

    backend_dir = Path(__file__).resolve().parent.parent
    db_url = f"postgresql+asyncpg://postgres:postres123@localhost:5432/{db_name}"
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["ENVIRONMENT"] = "testing"

    try:
        # Step 1: Migration & Check
        up_res = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=str(backend_dir), env=env, capture_output=True, text=True)
        assert up_res.returncode == 0, f"Upgrade failed: {up_res.stderr}"

        chk_res = subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=str(backend_dir), env=env, capture_output=True, text=True)
        assert chk_res.returncode == 0, f"Check failed: {chk_res.stdout}"
        assert "No new upgrade operations detected" in chk_res.stdout

        # Step 2: TestClient flow against this disposable DB
        from app.core.config import settings
        orig_db = settings.DATABASE_URL
        object.__setattr__(settings, "DATABASE_URL", db_url)

        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as client:
            # Register user
            user_email = f"bootstrap_user_{uuid.uuid4().hex[:6]}@example.com"
            reg_resp = client.post(
                "/api/v1/auth/register",
                json={
                    "email": user_email,
                    "password": "SecurePassword123!",
                    "full_name": "Bootstrap Verification User",
                },
            )
            assert reg_resp.status_code == 201
            assert reg_resp.json()["role"] in ("DEVELOPER", "VIEWER")

            # Login
            login_resp = client.post(
                "/api/v1/auth/login",
                json={"email": user_email, "password": "SecurePassword123!"},
            )
            assert login_resp.status_code == 200

            # Create first job
            job_resp = client.post(
                "/api/v1/jobs",
                json={
                    "name": "Bootstrap Verification Job",
                    "source_repository": "https://github.com/example/sample-repo.git",
                    "source_revision": "main",
                    "budget": 15000.0,
                },
            )
            assert job_resp.status_code == 201
            assert job_resp.json()["status"] in ("CREATED", "INTAKE")

        object.__setattr__(settings, "DATABASE_URL", orig_db)

    finally:
        manager.drop_database(db_name)
'''

content += flow_test
test_file.write_text(content, encoding="utf-8")
print("Added test_empty_db_bootstrap_to_first_job_flow to test_w03_schema_and_reconciliation.py")

