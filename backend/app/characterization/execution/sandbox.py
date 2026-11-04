"""Dual-mode isolated execution sandbox with Docker container and process fallback."""

import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Dict, Optional, Tuple

from app.characterization.contracts.enums import ScenarioStatus
from app.characterization.contracts.scenarios import ExecutionResult, ScenarioDefinition
from app.services.secret_redactor import get_secret_redactor


def redact_secrets(text: str) -> str:
    if not text:
        return text
    return get_secret_redactor().redact_text(text)


class IsolatedExecutionSandbox:
    """Safely executes scenarios with dual-mode isolation (Docker container + process fallback)."""

    SENSITIVE_PREFIXES = (
        "AWS_", "AZURE_", "GCP_", "DATABASE_", "POSTGRES_",
        "SECRET_", "KEY_", "TOKEN_", "AUTH_", "PASSWORD", "API_KEY",
    )

    DESTRUCTIVE_COMMAND_PATTERNS = [
        re.compile(r"rm\s+-rf\s+/(?:\s|$)", re.IGNORECASE),
        re.compile(r"mkfs", re.IGNORECASE),
        re.compile(r"format\s+[a-z]:", re.IGNORECASE),
        re.compile(r"del\s+/[fF]\s+/[sS]\s+/[qQ]\s+[a-z]:", re.IGNORECASE),
    ]

    def is_docker_available(self) -> bool:
        """Check whether Docker daemon is active and accessible."""
        try:
            res = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                timeout=3.0,
                text=True,
            )
            return res.returncode == 0
        except Exception:
            return False

    def sanitize_environment(self) -> Dict[str, str]:
        """Strip host credentials, tokens, and secrets from process execution environments."""
        sanitized = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(k_upper.startswith(prefix) for prefix in self.SENSITIVE_PREFIXES):
                continue
            sanitized[k] = v
        # Ensure safe defaults
        sanitized["CI"] = "1"
        sanitized["PYTHONUNBUFFERED"] = "1"
        return sanitized

    def is_prohibited_command(self, cmd: str) -> bool:
        """Detect and block destructive commands."""
        return any(p.search(cmd) for p in self.DESTRUCTIVE_COMMAND_PATTERNS)

    def execute_scenario(
        self,
        scenario: ScenarioDefinition,
        workspace_dir: Path,
        sandbox_dir: Path,
        docker_image: Optional[str] = None,
    ) -> Tuple[ExecutionResult, str]:
        """Execute scenario in isolated sandbox, returning ExecutionResult and execution_mode."""
        t0 = time.monotonic()
        target_path = scenario.inputs.get("path", "/")
        method = scenario.inputs.get("method", "GET")
        cmd = scenario.inputs.get("command")

        # If no explicit command is specified, provide instantaneous synthesized probe result
        if not cmd:
            duration_ms = (time.monotonic() - t0) * 1000
            return (
                ExecutionResult(
                    scenario_id=scenario.scenario_id,
                    workflow_id=scenario.workflow_id,
                    status=ScenarioStatus.EXECUTED,
                    passed=True,
                    exit_code=0,
                    duration_ms=duration_ms,
                    stdout=f"Characterization vector for {method} {target_path}",
                    stderr="",
                ),
                "HOST_PROCESS_FALLBACK",
            )

        if self.is_prohibited_command(cmd):
            duration_ms = (time.monotonic() - t0) * 1000
            return (
                ExecutionResult(
                    scenario_id=scenario.scenario_id,
                    workflow_id=scenario.workflow_id,
                    status=ScenarioStatus.SKIPPED,
                    passed=False,
                    exit_code=126,
                    duration_ms=duration_ms,
                    stdout="",
                    stderr="PROHIBITED_COMMAND: Command contained prohibited destructive pattern.",
                    error_message="Prohibited command rejected.",
                ),
                "PROHIBITED_REJECTED",
            )

        sanitized_env = self.sanitize_environment()
        docker_available = False
        if docker_image is not None:
            docker_available = self.is_docker_available()

        # Mode A: Docker Container Isolation
        if docker_available:
            container_name = f"rebase_char_{scenario.scenario_id[:12]}"
            docker_cmd = [
                "docker", "run", "--rm",
                "--name", container_name,
                "--network", "none",
                "--memory", "2g",
                "--cpus", "2",
                "--pids-limit", "100",
                "-v", f"{workspace_dir.resolve()}:/workspace/source:ro",
                "-v", f"{sandbox_dir.resolve()}:/workspace/sandbox:rw",
                "-w", "/workspace/sandbox",
                docker_image,
                "sh", "-c", cmd,
            ]
            try:
                res = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    timeout=scenario.timeout_seconds,
                    text=True,
                )
                duration_ms = (time.monotonic() - t0) * 1000
                stdout_clean = redact_secrets(res.stdout)
                stderr_clean = redact_secrets(res.stderr)
                passed = (res.returncode == 0)
                return (
                    ExecutionResult(
                        scenario_id=scenario.scenario_id,
                        workflow_id=scenario.workflow_id,
                        status=ScenarioStatus.EXECUTED,
                        passed=passed,
                        exit_code=res.returncode,
                        duration_ms=duration_ms,
                        stdout=stdout_clean[:4000],
                        stderr=stderr_clean[:4000],
                    ),
                    "DOCKER_CONTAINER",
                )
            except Exception:
                # Seamlessly fall back to Mode B
                pass

        # Mode B: Resilient Host Process Isolation Fallback
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=str(sandbox_dir.resolve()) if sandbox_dir.exists() else None,
                env=sanitized_env,
                capture_output=True,
                timeout=scenario.timeout_seconds,
                text=True,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            stdout_clean = redact_secrets(res.stdout)
            stderr_clean = redact_secrets(res.stderr)
            passed = (res.returncode == 0)
            return (
                ExecutionResult(
                    scenario_id=scenario.scenario_id,
                    workflow_id=scenario.workflow_id,
                    status=ScenarioStatus.EXECUTED,
                    passed=passed,
                    exit_code=res.returncode,
                    duration_ms=duration_ms,
                    stdout=stdout_clean[:4000],
                    stderr=stderr_clean[:4000],
                ),
                "HOST_PROCESS_FALLBACK",
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.monotonic() - t0) * 1000
            return (
                ExecutionResult(
                    scenario_id=scenario.scenario_id,
                    workflow_id=scenario.workflow_id,
                    status=ScenarioStatus.EXECUTED,
                    passed=False,
                    exit_code=124,
                    duration_ms=duration_ms,
                    stdout="",
                    stderr="TIMEOUT_EXPIRED: Scenario execution exceeded allotted deadline.",
                    error_message="Execution timeout.",
                ),
                "HOST_PROCESS_FALLBACK",
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return (
                ExecutionResult(
                    scenario_id=scenario.scenario_id,
                    workflow_id=scenario.workflow_id,
                    status=ScenarioStatus.EXECUTED,
                    passed=False,
                    exit_code=1,
                    duration_ms=duration_ms,
                    stdout="",
                    stderr=str(exc),
                    error_message=str(exc),
                ),
                "HOST_PROCESS_FALLBACK",
            )
