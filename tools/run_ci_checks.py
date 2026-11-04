"""Comprehensive CI validation script executing all W02 verification gates locally."""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
PYTHON_EXE = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
BLACK_EXE = BACKEND_DIR / ".venv" / "Scripts" / "black.exe"

def log_step(name: str):
    print("\n" + "=" * 80)
    print(f"  STEP: {name}")
    print("=" * 80)

def run_command(cmd: list[str], cwd: Path, env: dict = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    print(f"Running: {' '.join(str(c) for c in cmd)} (in {cwd})")
    start = time.time()
    res = subprocess.run(cmd, cwd=str(cwd), env=full_env, capture_output=True, text=True)
    duration = time.time() - start
    print(f"Exited with code {res.returncode} in {duration:.2f}s")
    if res.stdout:
        print("STDOUT:\n" + res.stdout.strip())
    if res.stderr:
        print("STDERR:\n" + res.stderr.strip())
    if res.returncode != 0:
        raise RuntimeError(f"Step failed with exit code {res.returncode}")
    return res

def main():
    print("================================================================================")
    print("   LEGACY MODERNIZATION PLATFORM: W02 CI & ISOLATION PIPELINE RUNNER")
    print("================================================================================")

    # 1. Code Formatting (Black)
    log_step("1. Python Code Formatting Check (Black)")
    run_command(
        [
            str(BLACK_EXE),
            "--check",
            "app/core/testing_infrastructure.py",
            "tests/test_w02_isolation_and_ci.py",
            "app/services/model_gateway.py",
            "tests/conftest.py",
            "tests/fixtures/fixture_loader.py",
        ],
        cwd=BACKEND_DIR,
    )

    # 2. Production DB Protection Guard (TEST-04 Proof)
    log_step("2. Production Database Access Refusal Guard Proof")
    probe_code = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "from app.core.testing_infrastructure import IsolationGuard, ProtectedResourceError\n"
        "try:\n"
        "    IsolationGuard.verify_database_url('postgresql://user:pass@localhost:5432/rebase')\n"
        "    sys.exit(1)\n"
        "except ProtectedResourceError as e:\n"
        "    print('SUCCESS: Production database properly refused:', e)\n"
    )
    run_command([str(PYTHON_EXE), "-c", probe_code], cwd=BACKEND_DIR)

    # 3. Hermetic Unit & Security Negative Tests
    log_step("3. Hermetic Unit & Security Negative Tests (Pytest)")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w02_isolation_and_ci.py",
            "-m",
            "unit or security_negative",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 4. Disposable Database Lifecycle Integration
    log_step("4. Disposable PostgreSQL Database Lifecycle (Create -> Migrate -> Drop)")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w02_isolation_and_ci.py",
            "-m",
            "db_integration",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 5. Full W01 Security Regression Suite
    log_step("5. W01 Security Regression Suite Verification")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w01_security.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 6. W03 Clean Bootstrap, Schema Drift & Data Reconciler Suite
    log_step("6. W03 Clean Bootstrap, Schema Drift & Reconciliation Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w03_schema_and_reconciliation.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 7. W04 Supervisor Authority & Command Pipeline Suite
    log_step("7. W04 Supervisor Authority & Command Pipeline Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w04_supervisor_authority.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 8. W05 Worker Dispatch, Leasing & Fencing Suite
    log_step("8. W05 Worker Dispatch, Leasing & Fencing Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w05_worker_dispatch.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 9. W06 Common Agent Runtime & Immutable Provenance Suite
    log_step("9. W06 Common Agent Runtime & Immutable Provenance Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w06_common_agent_runtime.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 10. W07 Real Characterizer & Schema/Data Execution Suite
    log_step("10. W07 Real Characterizer & Schema/Data Execution Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w07_characterizer_and_schema_data.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 11. W08 Planner DAG & Parallel Scheduler Suite
    log_step("11. W08 Planner DAG & Parallel Scheduler Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w08_planner_dag_and_scheduler.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 12. W09 E2B MicroVM Sandbox Isolation Suite
    log_step("12. W09 E2B MicroVM Sandbox Isolation Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_e2b_sandbox.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 13. W10 Independent Verifier & Reviewer Suite
    log_step("13. W10 Independent Verifier and Reviewer Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w10_independent_verifier.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 14. W11 Integration, G4 & Delivery Hardening Suite
    log_step("14. W11 Integration, G4 and Delivery Hardening Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w11_integration_and_delivery.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 15. W12 Truthful Workflow Projection & Frontend State Integrity Suite
    log_step("15. W12 Truthful Workflow Projection and Frontend State Integrity Suite")
    run_command(
        [
            str(PYTHON_EXE),
            "-m",
            "pytest",
            "-c",
            "pytest.ini",
            "tests/test_w12_workflow_projection.py",
            "-v",
        ],
        cwd=BACKEND_DIR,
    )

    # 16. Frontend Unit Tests (Vitest)
    log_step("16. Frontend Unit Tests (Vitest)")
    run_command(["npm.cmd", "test"], cwd=FRONTEND_DIR)

    # 17. Frontend Production Build (Vite)
    log_step("17. Frontend Production Build (Vite)")
    run_command(["npm.cmd", "run", "build"], cwd=FRONTEND_DIR)

    print("\n" + "=" * 80)
    print("   ALL W02 CI & ISOLATION GATES PASSED SUCCESSFULLY (100% VERIFIED)")
    print("=" * 80)

if __name__ == "__main__":
    main()
