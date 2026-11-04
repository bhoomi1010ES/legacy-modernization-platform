"""Comprehensive verification test suite for E2B MicroVM Sandbox integration."""

import os
import pytest
from app.core.config import settings
from app.core.errors import PlatformException
from app.services.e2b_sandbox_service import E2BSandboxService, isolated_e2b_sandbox


@pytest.fixture(autouse=True)
def ensure_e2b_key():
    """Ensure E2B_API_KEY is present from environment or config."""
    key = getattr(settings, "E2B_API_KEY", "") or os.getenv("E2B_API_KEY", "")
    if not key:
        pytest.skip("E2B_API_KEY not configured, skipping live sandbox tests")


def test_e2b_sandbox_connection_and_basic_execution():
    """Verify live E2B MicroVM creation, command execution, and exit codes."""
    svc = E2BSandboxService()
    assert svc.is_available() is True

    try:
        sandbox_id = svc.start(timeout_seconds=60)
        assert sandbox_id is not None
        assert len(sandbox_id) > 5

        # Execute uname -a in microvm
        result = svc.run_command("uname -a")
        assert result.exit_code == 0
        assert "linux" in result.stdout.lower()

        # Check unprivileged user
        who = svc.run_command("whoami")
        assert who.exit_code == 0
        assert who.stdout.strip() == "user"
    finally:
        svc.close()


def test_e2b_sandbox_file_roundtrip():
    """Verify writing files (including nested directories) and reading them back."""
    svc = E2BSandboxService()
    try:
        svc.start(timeout_seconds=60)
        files = {
            "main.py": "def add(a, b): return a + b\nprint('SUM:', add(2, 3))\n",
            "utils/math_helper.py": "# helper module\nPI = 3.14159\n",
        }
        written = svc.write_files(files, base_dir="/home/user/workspace")
        assert len(written) == 2
        assert "/home/user/workspace/main.py" in written
        assert "/home/user/workspace/utils/math_helper.py" in written

        # Read back main.py
        content = svc.read_file("/home/user/workspace/main.py")
        assert "def add(a, b)" in content

        # Execute the uploaded script
        res = svc.run_command("python3 /home/user/workspace/main.py")
        assert res.exit_code == 0
        assert "SUM: 5" in res.stdout
    finally:
        svc.close()


def test_e2b_sandbox_host_credential_isolation():
    """Verify that host environment variables (DATABASE_URL, SECRET_KEY, API keys) are NOT leaked to sandbox."""
    svc = E2BSandboxService()
    try:
        svc.start(timeout_seconds=60)

        # Run env inside sandbox
        res = svc.run_command("env")
        assert res.exit_code == 0
        output = res.stdout

        # Verify host secrets are absent
        forbidden = [
            "DATABASE_URL",
            "SECRET_KEY",
            "E2B_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "REDIS_URL",
        ]
        for var in forbidden:
            assert f"{var}=" not in output, f"Critical security leak: {var} found in sandbox environment!"

        # Attempt to pass a forbidden secret explicitly via env param
        malicious_env = {"DATABASE_URL": "postgresql://leaked_db", "SAFE_VAR": "hello"}
        res2 = svc.run_command("env", env=malicious_env)
        assert "DATABASE_URL=postgresql://leaked_db" not in res2.stdout
        assert "SAFE_VAR=hello" in res2.stdout
    finally:
        svc.close()


def test_e2b_sandbox_path_traversal_rejection():
    """Verify that path traversal attempts (../ or absolute paths) are rejected with UNSAFE_PATH_TRAVERSAL."""
    svc = E2BSandboxService()

    # 1. Traversal relative path
    with pytest.raises(PlatformException) as exc1:
        svc.validate_safe_relative_path("../../etc/passwd")
    assert exc1.value.code == "UNSAFE_PATH_TRAVERSAL"

    # 2. Absolute path
    with pytest.raises(PlatformException) as exc2:
        svc.validate_safe_relative_path("/root/.ssh/id_rsa")
    assert exc2.value.code == "UNSAFE_PATH_TRAVERSAL"

    # 3. Hidden traversal
    with pytest.raises(PlatformException) as exc3:
        svc.validate_safe_relative_path("foo/bar/../../../secret")
    assert exc3.value.code == "UNSAFE_PATH_TRAVERSAL"


def test_e2b_sandbox_bounded_checks_execution():
    """Verify execute_bounded_checks runs an entire compilation + test pipeline with attestation proof."""
    svc = E2BSandboxService()

    files = {
        "calculator.py": """
def multiply(x, y):
    return x * y
""",
        "test_calculator.py": """
from calculator import multiply

def test_multiply():
    assert multiply(3, 4) == 12
    assert multiply(-1, 5) == -5
""",
    }

    check_commands = [
        "python3 -m py_compile calculator.py",
        "python3 -c \"from test_calculator import test_multiply; test_multiply(); print('TESTS_PASSED')\"",
    ]

    proof = svc.execute_bounded_checks(
        files=files,
        check_commands=check_commands,
        base_dir="/home/user/calc_project",
        timeout_seconds=90,
    )

    assert proof.passed is True
    assert proof.exit_code == 0
    assert len(proof.commands_executed) == 2
    assert proof.attestation_digest != ""
    assert proof.completed_at is not None
    assert "calculator.py" in str(proof.files_written)


def test_e2b_sandbox_failing_command_containment():
    """Verify that syntax errors and failing tests in untrusted code are cleanly caught without crashing the host."""
    svc = E2BSandboxService()

    files = {
        "bad_code.py": "def syntax_error_here\n",
    }

    check_commands = [
        "python3 -m py_compile bad_code.py",
    ]

    proof = svc.execute_bounded_checks(
        files=files,
        check_commands=check_commands,
        base_dir="/home/user/bad_project",
        timeout_seconds=60,
    )

    assert proof.passed is False
    assert proof.exit_code != 0
    assert len(proof.commands_executed) == 1
    assert "SyntaxError" in proof.commands_executed[0].stderr or "SyntaxError" in proof.commands_executed[0].stdout
