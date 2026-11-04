"""E2B MicroVM Sandboxing Service.

Provides hardware-virtualized, ephemeral Firecracker MicroVM execution for
untrusted customer repositories, CodeWriter generation, and independent verification.
Eliminates host exposure: no Docker socket mounts, no host DB or secret leaks,
running as a non-root unprivileged user in the cloud.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import PurePosixPath
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.errors import PlatformException

logger = logging.getLogger(__name__)

# Bounded output limit (2MB) to prevent memory exhaustion from runaway commands
MAX_OUTPUT_BYTES = 2 * 1024 * 1024

# Host environment variables that MUST NEVER be passed to the untrusted sandbox
FORBIDDEN_ENV_VARS = {
    "DATABASE_URL",
    "SECRET_KEY",
    "E2B_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "REDIS_URL",
    "SANDBOX_DISPATCH_KEY",
    "SANDBOX_ATTESTATION_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
}


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    output_truncated: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass
class SandboxExecutionProof:
    sandbox_id: str
    runtime: str = "e2b-microvm"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    commands_executed: List[CommandResult] = field(default_factory=list)
    files_written: List[str] = field(default_factory=list)
    files_read: List[str] = field(default_factory=list)
    attestation_digest: str = ""
    exit_code: int = 0
    passed: bool = True
    error_message: Optional[str] = None


class E2BSandboxService:
    """Enterprise MicroVM Sandbox client using E2B."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "E2B_API_KEY", "") or os.getenv("E2B_API_KEY", "")
        if not self.api_key:
            raise PlatformException(
                code="E2B_CONFIG_MISSING",
                message="E2B_API_KEY is not configured in settings or environment.",
                status_code=500,
            )
        # Ensure E2B SDK recognizes the API key
        os.environ["E2B_API_KEY"] = self.api_key
        self._sandbox = None

    def is_available(self) -> bool:
        """Check if E2B is available and properly configured."""
        return bool(self.api_key and self.api_key.startswith("e2b_"))

    def start(self, timeout_seconds: int = 300) -> str:
        """Synchronously launch an isolated E2B MicroVM sandbox."""
        from e2b import Sandbox

        logger.info("Initializing E2B Sandbox with timeout=%ds...", timeout_seconds)
        self._sandbox = Sandbox.create(timeout=timeout_seconds)
        sandbox_id = self._sandbox.sandbox_id
        # Ensure default workspace directory exists
        self._sandbox.commands.run("mkdir -p /home/user/workspace")
        logger.info("E2B Sandbox started successfully. sandbox_id=%s", sandbox_id)
        return sandbox_id

    def close(self) -> None:
        """Terminate the MicroVM and release resources."""
        if self._sandbox is not None:
            try:
                self._sandbox.kill()
                logger.info("E2B Sandbox terminated. sandbox_id=%s", self._sandbox.sandbox_id)
            except Exception as e:
                logger.warning("Error killing E2B sandbox %s: %s", getattr(self._sandbox, "sandbox_id", "unknown"), e)
            finally:
                self._sandbox = None

    def validate_safe_relative_path(self, path_str: str) -> str:
        """Enforces that paths are strictly relative, with no ../ directory traversal."""
        normalized = PurePosixPath(path_str.replace("\\", "/"))
        if normalized.is_absolute():
            raise PlatformException(
                code="UNSAFE_PATH_TRAVERSAL",
                message=f"Absolute paths forbidden in sandbox workspace: '{path_str}'",
                status_code=400,
            )
        parts = normalized.parts
        if ".." in parts:
            raise PlatformException(
                code="UNSAFE_PATH_TRAVERSAL",
                message=f"Directory traversal ('..') forbidden in sandbox workspace: '{path_str}'",
                status_code=400,
            )
        return str(normalized)

    def write_files(self, files: Dict[str, str | bytes], base_dir: str = "/home/user/workspace") -> List[str]:
        """Uploads files to the sandbox workspace with path safety verification."""
        if self._sandbox is None:
            raise PlatformException(code="SANDBOX_NOT_STARTED", message="Sandbox is not running.", status_code=500)

        # Ensure base directory exists in sandbox
        self._sandbox.commands.run(f"mkdir -p '{base_dir}'")
        written_paths = []

        for rel_path, content in files.items():
            safe_rel = self.validate_safe_relative_path(rel_path)
            full_path = f"{base_dir.rstrip('/')}/{safe_rel}"

            # Ensure parent directories exist
            parent_dir = str(PurePosixPath(full_path).parent)
            self._sandbox.commands.run(f"mkdir -p '{parent_dir}'")

            # Write file content
            if isinstance(content, bytes):
                content_str = content.decode("utf-8", errors="replace")
            else:
                content_str = str(content)

            self._sandbox.files.write(full_path, content_str)
            written_paths.append(full_path)

        return written_paths

    def read_file(self, file_path: str) -> str:
        """Reads a file from the sandbox."""
        if self._sandbox is None:
            raise PlatformException(code="SANDBOX_NOT_STARTED", message="Sandbox is not running.", status_code=500)
        return self._sandbox.files.read(file_path)

    def run_command(
        self,
        command: str,
        cwd: str = "/home/user/workspace",
        env: Optional[Dict[str, str]] = None,
        timeout: int = 60,
    ) -> CommandResult:
        """Executes a command inside the isolated microVM with strict security filtering."""
        if self._sandbox is None:
            raise PlatformException(code="SANDBOX_NOT_STARTED", message="Sandbox is not running.", status_code=500)

        # Sanitize env vars: NEVER leak host secrets
        safe_env = {}
        if env:
            for k, v in env.items():
                if k.upper() in FORBIDDEN_ENV_VARS:
                    logger.warning("Redacted forbidden host env var '%s' from sandbox execution.", k)
                    continue
                safe_env[k] = str(v)

        start_time = time.monotonic()
        try:
            if cwd:
                self._sandbox.commands.run(f"mkdir -p '{cwd}'")
            # e2b commands.run
            exec_res = self._sandbox.commands.run(
                cmd=command,
                cwd=cwd,
                envs=safe_env if safe_env else None,
                timeout=timeout,
            )
            duration = time.monotonic() - start_time

            stdout = exec_res.stdout or ""
            stderr = exec_res.stderr or ""
            truncated = False

            if len(stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
                stdout = stdout[:MAX_OUTPUT_BYTES] + "\n[TRUNCATED: Exceeded output limit]"
                truncated = True
            if len(stderr.encode("utf-8")) > MAX_OUTPUT_BYTES:
                stderr = stderr[:MAX_OUTPUT_BYTES] + "\n[TRUNCATED: Exceeded output limit]"
                truncated = True

            return CommandResult(
                command=command,
                exit_code=exec_res.exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=round(duration, 3),
                output_truncated=truncated,
            )
        except Exception as e:
            duration = time.monotonic() - start_time
            return CommandResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"Execution error or timeout: {str(e)}",
                duration_seconds=round(duration, 3),
                output_truncated=False,
            )

    def execute_bounded_checks(
        self,
        files: Dict[str, str | bytes],
        check_commands: List[str],
        base_dir: str = "/home/user/workspace",
        timeout_seconds: int = 180,
    ) -> SandboxExecutionProof:
        """Full atomic sandbox run: start MicroVM, write files, run checks, gather attestation, and cleanup."""
        proof = SandboxExecutionProof(sandbox_id="pending")
        try:
            sandbox_id = self.start(timeout_seconds=timeout_seconds)
            proof.sandbox_id = sandbox_id

            # Upload files
            written = self.write_files(files, base_dir=base_dir)
            proof.files_written = written

            # Execute all check commands sequentially
            all_passed = True
            overall_exit = 0

            for cmd in check_commands:
                res = self.run_command(cmd, cwd=base_dir, timeout=60)
                proof.commands_executed.append(res)
                if not res.passed:
                    all_passed = False
                    overall_exit = res.exit_code
                    break

            proof.passed = all_passed
            proof.exit_code = overall_exit
            proof.completed_at = datetime.now(timezone.utc)

            # Compute cryptographic attestation digest
            summary = {
                "sandbox_id": sandbox_id,
                "runtime": proof.runtime,
                "files_count": len(written),
                "passed": proof.passed,
                "exit_code": proof.exit_code,
                "commands_count": len(proof.commands_executed),
                "completed_at": proof.completed_at.isoformat(),
            }
            proof.attestation_digest = hashlib.sha256(json.dumps(summary, sort_keys=True).encode()).hexdigest()
            return proof
        except Exception as e:
            proof.passed = False
            proof.exit_code = 1
            proof.error_message = str(e)
            proof.completed_at = datetime.now(timezone.utc)
            return proof
        finally:
            self.close()


@asynccontextmanager
async def isolated_e2b_sandbox(timeout_seconds: int = 180) -> AsyncGenerator[E2BSandboxService, None]:
    """Async context manager guaranteeing cleanup of E2B microVM."""
    svc = E2BSandboxService()
    svc.start(timeout_seconds=timeout_seconds)
    try:
        yield svc
    finally:
        svc.close()
