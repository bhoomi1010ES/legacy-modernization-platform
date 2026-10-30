"""Subprocess execution helper resilient to Windows event loop differences.

On Windows, `asyncio.create_subprocess_exec` requires `asyncio.ProactorEventLoop`.
Under Uvicorn/AnyIO or reload mode, a `SelectorEventLoop` is often active, causing
`NotImplementedError` when creating asyncio subprocesses.

This module provides `run_subprocess_async`, which executes standard subprocesses
in worker threads via `asyncio.to_thread` with streaming/communication bounds,
ensuring reliable execution on any platform and under any event loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class SubprocessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


async def run_subprocess_async(
    args: List[str],
    *,
    input_data: Optional[bytes] = None,
    timeout: Optional[float] = 30.0,
    cwd: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    max_output_bytes: int = 1048576,
) -> SubprocessResult:
    """Runs a subprocess asynchronously using a thread pool worker to bypass loop restrictions."""
    def _execute() -> SubprocessResult:
        p = subprocess.Popen(
            args,
            stdin=subprocess.PIPE if input_data is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        try:
            stdout, stderr = p.communicate(input=input_data, timeout=timeout)
            if len(stdout) > max_output_bytes:
                stdout = stdout[:max_output_bytes]
            if len(stderr) > max_output_bytes:
                stderr = stderr[:max_output_bytes]
            return SubprocessResult(
                returncode=p.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            p.kill()
            try:
                stdout, stderr = p.communicate(timeout=2.0)
            except Exception:
                stdout, stderr = b"", b""
            raise asyncio.TimeoutError(f"Subprocess timed out after {timeout} seconds")
        except Exception:
            p.kill()
            raise

    return await asyncio.to_thread(_execute)

