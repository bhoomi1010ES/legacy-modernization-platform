import pathlib

p = pathlib.Path("tools/run_ci_checks.py")
content = p.read_text(encoding="utf-8")

old_section = """    # 14. W11 Integration, G4 & Delivery Hardening Suite
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

    # 15. Frontend Unit Tests (Vitest)
    log_step("15. Frontend Unit Tests (Vitest)")
    run_command(["npm.cmd", "test"], cwd=FRONTEND_DIR)

    # 16. Frontend Production Build
    log_step("16. Frontend Production Build (Vite)")
    run_command(["npm.cmd", "run", "build"], cwd=FRONTEND_DIR)"""

new_section = """    # 14. W11 Integration, G4 & Delivery Hardening Suite
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
    run_command(["npm.cmd", "run", "build"], cwd=FRONTEND_DIR)"""

if old_section in content:
    content = content.replace(old_section, new_section, 1)
else:
    old_crlf = old_section.replace("\n", "\r\n")
    new_crlf = new_section.replace("\n", "\r\n")
    assert old_crlf in content, "old_section not found in run_ci_checks.py"
    content = content.replace(old_crlf, new_crlf, 1)

p.write_text(content, encoding="utf-8")
print("Successfully updated tools/run_ci_checks.py")

