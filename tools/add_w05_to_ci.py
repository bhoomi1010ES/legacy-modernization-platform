with open("tools/run_ci_checks.py", "r", encoding="utf-8") as f:
    c = f.read()

old_block = """# 7. W04 Supervisor Authority & Command Pipeline Suite
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

    # 8. Frontend Unit Tests (Vitest)
    log_step("8. Frontend Unit Tests (Vitest)")
    run_command(["npm.cmd", "test"], cwd=FRONTEND_DIR)

    # 9. Frontend Production Build
    log_step("9. Frontend Production Build (Vite)")
    run_command(["npm.cmd", "run", "build"], cwd=FRONTEND_DIR)"""

new_block = """# 7. W04 Supervisor Authority & Command Pipeline Suite
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

    # 9. Frontend Unit Tests (Vitest)
    log_step("9. Frontend Unit Tests (Vitest)")
    run_command(["npm.cmd", "test"], cwd=FRONTEND_DIR)

    # 10. Frontend Production Build
    log_step("10. Frontend Production Build (Vite)")
    run_command(["npm.cmd", "run", "build"], cwd=FRONTEND_DIR)"""

c_norm = c.replace("\r\n", "\n")
old_norm = old_block.replace("\r\n", "\n")
new_norm = new_block.replace("\r\n", "\n")

assert old_norm in c_norm, "old_block not found in run_ci_checks.py"
c_norm = c_norm.replace(old_norm, new_norm, 1)

with open("tools/run_ci_checks.py", "w", encoding="utf-8") as f:
    f.write(c_norm)

print("Updated run_ci_checks.py with W05 step successfully")

