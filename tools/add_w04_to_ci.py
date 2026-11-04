path = r"tools/run_ci_checks.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = '''    # 7. Frontend Unit Tests (Vitest)
    log_step("7. Frontend Unit Tests (Vitest)")
    run_command(["npm.cmd", "test"], cwd=FRONTEND_DIR)

    # 7. Frontend Production Build
    log_step("8. Frontend Production Build (Vite)")
    run_command(["npm.cmd", "run", "build"], cwd=FRONTEND_DIR)'''

rep = '''    # 7. W04 Supervisor Authority & Command Pipeline Suite
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
    run_command(["npm.cmd", "run", "build"], cwd=FRONTEND_DIR)'''

assert target in c, "target not found in run_ci_checks.py"
c = c.replace(target, rep, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("Updated run_ci_checks.py with Step 7 for W04")

