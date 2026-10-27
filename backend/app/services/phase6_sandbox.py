"""Independent Docker verifier: no host mounts, network, shell input or image pulling."""

import asyncio
import json
import logging
import re
import uuid
from time import monotonic
from pathlib import PurePosixPath
from app.core.config import settings
from app.schemas.phase6 import CheckSpec
from app.services.phase5_engine import (
    canonical,
    digest,
    normalize,
    read_bounded,
    strict_adapter_object,
    reject_json_constant,
)
from app.schemas.phase5 import NormalizationRule
from app.services.secret_redactor import get_secret_redactor

logger = logging.getLogger(__name__)

# This trusted harness is the entrypoint, never generated or editable by CodeWriter.
HARNESS = r"""
import json, pathlib, subprocess, sys, time, os, hashlib
payload=json.load(sys.stdin)
root=pathlib.Path('/work')
root.mkdir(exist_ok=True)
for name, content in payload['files'].items():
    path=root/name
    if path.is_absolute() and root not in path.parents: raise ValueError('unsafe snapshot')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(content,encoding='utf-8')
def fingerprint():
    return {n: hashlib.sha256((root/n).read_bytes()).hexdigest() if (root/n).is_file() else None for n in payload['files']}
initial=fingerprint()
results=[]
for check in payload['checks']:
    start=time.monotonic()
    try:
        run=subprocess.run(check['command'],cwd=root,input='',capture_output=True,text=True,timeout=30,shell=False)
        results.append(dict(category=check['category'],command=check['command'],exit_code=run.returncode,duration_ms=(time.monotonic()-start)*1000,stdout=run.stdout[:32768],stderr=run.stderr[:32768]))
    except subprocess.TimeoutExpired:
        results.append(dict(category=check['category'],command=check['command'],exit_code=None,duration_ms=(time.monotonic()-start)*1000,status='TIMEOUT'))
    except OSError:
        results.append(dict(category=check['category'],command=check['command'],exit_code=None,duration_ms=(time.monotonic()-start)*1000,status='UNAVAILABLE',stderr='Configured executable is unavailable'))
observations=[]
for case in payload['cases']:
    start=time.monotonic()
    try:
        run=subprocess.run(payload['adapter'],cwd=root,input=json.dumps(dict(scenario=case['name'],inputs=case['fixtures'])),capture_output=True,text=True,timeout=30,shell=False)
        observations.append(dict(test_case_id=case['test_case_id'],command=payload['adapter'],exit_code=run.returncode,duration_ms=(time.monotonic()-start)*1000,stdout=run.stdout[:65536],stderr=run.stderr[:32768]))
    except subprocess.TimeoutExpired:
        observations.append(dict(test_case_id=case['test_case_id'],command=payload['adapter'],exit_code=None,duration_ms=(time.monotonic()-start)*1000,status='TIMEOUT'))
    except OSError:
        observations.append(dict(test_case_id=case['test_case_id'],command=payload['adapter'],exit_code=None,duration_ms=(time.monotonic()-start)*1000,status='UNAVAILABLE'))
print(json.dumps(dict(checks=results,observations=observations,source_unchanged=initial==fingerprint()),allow_nan=False))
"""


def approved_command(command: list[str], *, adapter: bool = False) -> bool:
    try:
        if not command or any(
            any(c in arg for c in (";", "|", "&", "`", "$", "\n", "\r", "\x00"))
            for arg in command
        ):
            return False
        executable = PurePosixPath(command[0]).name
        if executable == "syft" and not adapter:
            return command in (["syft", "version", "-o", "json"], ["syft", "scan", "dir:/work", "-o", "syft-json"])
        if executable in {"python", "python3"}:
            if adapter:
                return (
                    len(command) == 2
                    and command[1].startswith("/")
                    and ".." not in PurePosixPath(command[1]).parts
                    and len(PurePosixPath(command[1]).parts) > 1
                    and PurePosixPath(command[1]).parts[1] not in {"work", "tmp"}
                    and command[1].endswith(".py")
                )
            return (
                len(command) >= 3
                and command[1] == "-m"
                and command[2] in {"compileall", "pytest", "mypy", "ruff", "bandit"}
                and "-c" not in command
                and "--override-ini" not in command
            )
        return not adapter and (
            executable in {"pytest", "tsc", "mypy", "ruff", "bandit"}
            or (
                executable in {"npm", "npm.cmd"}
                and len(command) == 3
                and command[1] == "run"
                and command[2] in {"build", "test", "lint", "typecheck", "security"}
            )
        )
    except Exception:
        logger.exception("phase6.approved_command failed")
        raise


def configuration() -> tuple[str, list[dict], list[str]]:
    try:
        image = settings.PHASE6_SANDBOX_IMAGE
        checks = [
            CheckSpec.model_validate(c).model_dump()
            for c in json.loads(settings.PHASE6_CHECK_COMMANDS_JSON)
        ]
        adapter = json.loads(settings.PHASE6_TARGET_COMMAND_JSON)
        if (
            not image
            or image.startswith("-")
            or not re.fullmatch(r"[A-Za-z0-9./:_@-]+", image)
        ):
            raise ValueError("PHASE6_SANDBOX_IMAGE is not configured")
        if {c["category"] for c in checks} != {"build", "unit", "static", "security"}:
            raise ValueError("Build, unit, static and security commands are required")
        if (
            not all(approved_command(c["command"]) for c in checks)
            or not isinstance(adapter, list)
            or not approved_command(adapter, adapter=True)
        ):
            raise ValueError("Unsafe or missing sandbox command configuration")
        return image, checks, adapter
    except Exception:
        logger.exception("phase6.configuration unavailable")
        raise


async def local_image(image: str) -> str:
    """Resolve a local immutable image ID without pulling or trusting a mutable tag."""
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}}",
            image,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        identity = output.decode().strip()
        if process.returncode or not re.fullmatch(r"sha256:[a-f0-9]{64}", identity):
            raise ValueError(
                "Configured local image is unavailable; image pulling is disabled"
            )
        return identity
    except Exception:
        logger.exception("phase6.local_image unavailable")
        raise
    finally:
        if process and process.returncode is None:
            process.kill()
            await process.wait()


async def execute(files: dict[str, str], cases: list[dict], baseline_hash: str, *, system_checks: list[dict] | None = None) -> dict:
    process = None
    name = f"phase6-{uuid.uuid4().hex}"
    start = monotonic()
    try:
        image, checks, adapter = configuration()
        if system_checks is not None:
            from app.schemas.phase7 import SystemCheck
            checks = [SystemCheck.model_validate(c).model_dump() for c in system_checks]
            if not {"build", "unit", "integration", "static", "security"}.issubset({c["category"] for c in checks}) or not all(approved_command(c["command"]) for c in checks):
                raise ValueError("Complete administrator-approved system checks are required")
        image = await local_image(image)
        payload = {
            "files": files,
            "cases": [
                {k: case[k] for k in ("test_case_id", "name", "fixtures")}
                for case in cases
            ],
            "checks": checks,
            "adapter": adapter,
        }
        fingerprint = digest(
            {
                "files": files,
                "baseline_hash": baseline_hash,
                "image": image,
                "checks": checks,
                "adapter": adapter,
            }
        )
        process = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--pull=never",
            "--network=none",
            "--read-only",
            "--memory=256m",
            "--cpus=1",
            "--pids-limit=64",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65534:65534",
            "--log-driver=none",
            "--tmpfs=/work:rw,nosuid,nodev,size=128m,mode=1777",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
            "--entrypoint",
            settings.PHASE6_SANDBOX_PYTHON,
            "-i",
            image,
            "-I",
            "-c",
            HARNESS,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def send():
            try:
                process.stdin.write(canonical(payload))
                await process.stdin.drain()
                process.stdin.close()
            except Exception:
                logger.exception("phase6.execute stdin failed")
                raise

        if process.stdout is None or process.stderr is None:
            raise ValueError("Sandbox output streams are unavailable")
        _, stdout, stderr, _ = await asyncio.wait_for(
            asyncio.gather(
                send(),
                read_bounded(process.stdout),
                read_bounded(process.stderr),
                process.wait(),
            ),
            timeout=settings.PHASE6_SANDBOX_TIMEOUT,
        )
        if process.returncode:
            return {
                "available": False,
                "reason": f"Sandbox unavailable or failed (exit {process.returncode}); no verification evidence accepted",
                "checks": [],
                "cases": [],
            }
        data = json.loads(
            stdout,
            object_pairs_hook=strict_adapter_object,
            parse_constant=reject_json_constant,
        )
        assessed = assess(data, cases, checks, fingerprint)
        assessed["image_id"] = image
        assessed["container_name"] = name
        assessed["duration_ms"] = (monotonic() - start) * 1000
        return assessed
    except Exception as exc:
        logger.exception(
            "phase6.execute unavailable | error_type=%s", type(exc).__name__
        )
        return {
            "available": False,
            "reason": "Sandbox configuration, image, daemon, deadline or output validation unavailable",
            "checks": [],
            "cases": [],
            "duration_ms": (monotonic() - start) * 1000,
        }
    finally:
        if process:
            if process.returncode is None:
                process.kill()
                await process.wait()
            try:
                cleanup = await asyncio.create_subprocess_exec(
                    "docker",
                    "rm",
                    "--force",
                    name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(cleanup.wait(), timeout=10)
            except Exception:
                logger.exception("phase6.execute cleanup failed | container=%s", name)


def assess(data: dict, cases: list[dict], specs: list[dict], fingerprint: str) -> dict:
    """Host-side deterministic comparison; adapters never supply pass/fail or expected outputs."""
    try:
        if (
            set(data) != {"checks", "observations", "source_unchanged"}
            or len(data["checks"]) != len(specs)
            or len(data["observations"]) != len(cases)
        ):
            raise ValueError("Incomplete independent execution evidence")
        checks, results = [], []
        for item, spec in zip(data["checks"], specs):
            if (
                item["category"] != spec["category"]
                or item["command"] != spec["command"]
                or not isinstance(item["duration_ms"], (float, int))
            ):
                raise ValueError("Check evidence identity mismatch")
            checks.append(
                {
                    **item,
                    "status": (
                        "PASS"
                        if type(item.get("exit_code")) is int and item["exit_code"] == 0
                        else "FAIL"
                    ),
                    "artifact_hash": fingerprint,
                }
            )
        for observed, case in zip(data["observations"], cases):
            if observed["test_case_id"] != case["test_case_id"]:
                raise ValueError("Frozen test evidence mismatch")
            actual = None
            match = False
            if type(observed.get("exit_code")) is int and observed["exit_code"] == 0:
                actual = json.loads(
                    observed["stdout"],
                    object_pairs_hook=strict_adapter_object,
                    parse_constant=reject_json_constant,
                )
                if not isinstance(actual, dict) or set(actual) != {
                    "output",
                    "side_effects",
                }:
                    raise ValueError("Target adapter observation contract violated")
                rules = [
                    NormalizationRule.model_validate(r) for r in case["normalization"]
                ]
                match = canonical(normalize(actual["output"], rules)) == canonical(
                    normalize(case["expected"], rules)
                ) and canonical(actual["side_effects"]) == canonical(
                    case["side_effects"]
                )
            results.append(
                {
                    "test_case_id": case["test_case_id"],
                    "actual": actual,
                    "status": "PASS" if match else "FAIL",
                    "command": observed["command"],
                    "exit_code": observed.get("exit_code"),
                    "duration_ms": observed["duration_ms"],
                    "artifact_hash": fingerprint,
                }
            )
        passed = (
            bool(cases)
            and data["source_unchanged"] is True
            and all(c["status"] == "PASS" for c in checks + results)
        )
        return get_secret_redactor().redact_object(
            {
                "available": True,
                "passed": passed,
                "checks": checks,
                "cases": results,
                "artifact_hash": fingerprint,
                "source_unchanged": data["source_unchanged"],
            }
        )
    except Exception:
        logger.exception("phase6.assess failed")
        raise
