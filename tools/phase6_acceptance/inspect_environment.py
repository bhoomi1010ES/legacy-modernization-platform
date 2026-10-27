"""Observe the actual sandbox container while existing Verifier execution is running."""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402 -- standalone backend bootstrap
from app.services.phase6_sandbox import execute  # noqa: E402

logger = logging.getLogger(__name__)


async def docker(*args: str) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, error = await asyncio.wait_for(process.communicate(), timeout=15)
        if process.returncode:
            raise RuntimeError(
                f"Docker inspection failed with exit {process.returncode}"
            )
        return output.decode().strip()
    except Exception:
        logger.exception("inspect_environment.docker failed")
        raise


async def main() -> None:
    task = None
    try:
        folder = ROOT / "artifacts/phase6-real-acceptance"
        frozen = json.loads((folder / "g2-review.json").read_text())["characterization"]
        plan = json.loads((folder / "g3-review.json").read_text())["plan"][
            "conversion_plan"
        ]
        target = plan["modules"][0]["target_scope"][0] + "/calc.py"
        initial = set(
            (
                await docker("ps", "--filter", "name=phase6-", "--format", "{{.Names}}")
            ).splitlines()
        )
        task = asyncio.create_task(
            execute(
                {target: "def add(x: int, y: int) -> int:\n    return x + y\n"},
                frozen["cases"],
                frozen["content_hash"],
            )
        )
        observed = None
        for _ in range(100):
            current = (
                set(
                    (
                        await docker(
                            "ps", "--filter", "name=phase6-", "--format", "{{.Names}}"
                        )
                    ).splitlines()
                )
                - initial
            )
            if current:
                observed = json.loads(await docker("inspect", sorted(current)[0]))[0]
                break
            if task.done():
                break
            await asyncio.sleep(0.1)
        if observed is None:
            raise RuntimeError("Could not observe the actual acceptance container")
        host = observed["HostConfig"]
        assert host["NetworkMode"] == "none"
        assert host["ReadonlyRootfs"] is True
        assert host["Memory"] == 268435456 and host["NanoCpus"] == 1000000000
        assert host["PidsLimit"] == 64 and host["CapDrop"] == ["ALL"]
        assert "no-new-privileges" in host["SecurityOpt"]
        assert not host.get("Binds") and not host.get("Mounts")
        assert all(mount["Type"] == "tmpfs" for mount in observed["Mounts"])
        assert observed["Config"]["User"] == "65534:65534"
        assert not any(
            any(
                token in entry.split("=", 1)[0]
                for token in ("KEY", "PASSWORD", "SECRET", "TOKEN", "DATABASE")
            )
            for entry in observed["Config"]["Env"]
        )
        verification = await task
        remaining = (
            await docker(
                "ps",
                "-a",
                "--filter",
                f"name={observed['Name'].lstrip('/')}",
                "--format",
                "{{.Names}}",
            )
        ).splitlines()
        assert not remaining
        # Hash bytes in the actual pinned image, not potentially reformatted build inputs.
        hashes = await docker(
            "run",
            "--rm",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--memory=256m",
            "--cpus=1",
            "--pids-limit=64",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user=65534:65534",
            "--entrypoint",
            "python",
            settings.PHASE6_SANDBOX_IMAGE,
            "-I",
            "-c",
            "import hashlib,json,pathlib; print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['/adapter.py','/legacy_adapter.py','/legacy/calc.py','/acceptance/test_calc.py','/acceptance/test_security.py']}))",
        )
        evidence = {
            "scope": "Trusted probe at the actual approved target path, not CodeWriter output",
            "container_id": observed["Id"],
            "container_name": observed["Name"],
            "image_id": observed["Image"],
            "host_config": {
                key: host.get(key)
                for key in (
                    "NetworkMode",
                    "ReadonlyRootfs",
                    "Memory",
                    "NanoCpus",
                    "PidsLimit",
                    "CapDrop",
                    "SecurityOpt",
                    "Binds",
                    "Mounts",
                    "Tmpfs",
                    "AutoRemove",
                    "LogConfig",
                )
            },
            "mounts": observed["Mounts"],
            "user": observed["Config"]["User"],
            "environment_variable_names": [
                entry.split("=", 1)[0] for entry in observed["Config"]["Env"]
            ],
            "cleanup_confirmed": True,
            "image_file_sha256": json.loads(hashes),
            "target_path": target,
            "verification": verification,
        }
        raw = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        (folder / "environment.json").write_bytes(raw)
        print(
            json.dumps(
                {"evidence_sha256": hashlib.sha256(raw).hexdigest(), **evidence},
                indent=2,
            )
        )
    except Exception:
        logger.exception("inspect_environment.main failed")
        raise
    finally:
        if task and not task.done():
            await task


if __name__ == "__main__":
    asyncio.run(main())
