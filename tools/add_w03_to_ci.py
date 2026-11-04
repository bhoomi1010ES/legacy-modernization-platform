from pathlib import Path

path = Path("tools/run_ci_checks.py")
content = path.read_text(encoding="utf-8")

old_part = '''    # 5. Full W01 Security Regression Suite
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

    # 6. Frontend Unit Tests (Vitest)
    log_step("6. Frontend Unit Tests (Vitest)")'''

new_part = '''    # 5. Full W01 Security Regression Suite
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

    # 7. Frontend Unit Tests (Vitest)
    log_step("7. Frontend Unit Tests (Vitest)")'''

content = content.replace(old_part, new_part, 1)
content = content.replace('log_step("7. Frontend Production Build (Vite)")', 'log_step("8. Frontend Production Build (Vite)")')
path.write_text(content, encoding="utf-8")
print("Updated run_ci_checks.py with W03 step.")

