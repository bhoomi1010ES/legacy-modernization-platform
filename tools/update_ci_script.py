PATH = "tools/run_ci_checks.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

target = """    # 10. W07 Real Characterizer & Schema/Data Execution Suite
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

    # 11. Frontend Unit Tests (Vitest)
    log_step("11. Frontend Unit Tests (Vitest)")"""

replacement = """    # 10. W07 Real Characterizer & Schema/Data Execution Suite
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

    # 13. Frontend Unit Tests (Vitest)
    log_step("13. Frontend Unit Tests (Vitest)")"""

assert target in content, "Target not found in run_ci_checks.py"
content = content.replace(target, replacement, 1)
content = content.replace("# 12. Frontend Production Build", "# 14. Frontend Production Build")
content = content.replace('log_step("12. Frontend Production Build (Vite)")', 'log_step("14. Frontend Production Build (Vite)")')

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated run_ci_checks.py successfully.")

