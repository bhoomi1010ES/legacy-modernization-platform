"""Real Docker failure probes against the human-frozen legacy observations."""

# Standalone runner intentionally bootstraps backend imports below.
# ruff: noqa: E402

import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.phase5_engine import (
    canonical,
    digest,
)  # noqa: E402 -- backend bootstrap
from app.services.phase6_sandbox import execute  # noqa: E402
from app.services.reviewer_agent import review  # noqa: E402

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        folder = ROOT / "artifacts/phase6-real-acceptance"
        frozen = json.loads((folder / "g2-review.json").read_text())["characterization"]
        cases = frozen["cases"]
        probes = {
            "BUILD_FAILED": "def add(x, y):\n    return (\n",
            "UNIT_FAILED_REGRESSION": "def add(x: int, y: int) -> int:\n    return x - y\n",
            "STATIC_FAILED": "def add(x: int, y: int) -> str:\n    return x + y\n",
            "REVIEW_BLOCKED": 'def add(x: int, y: int) -> int:\n    return eval("x + y")\n',
            "UNOBSERVED": "def add(x: int, y: int) -> int:\n    return x + y\n",
        }
        results = []
        for label, source in probes.items():
            files = {"modern/calc.py": source}
            verification = await execute(
                files, [] if label == "UNOBSERVED" else cases, frozen["content_hash"]
            )
            reviewer = review(
                files, [{"symbol": "add"}], digest(files), execution=verification
            )
            if (
                not verification.get("available")
                or verification.get("passed") is not False
            ):
                raise RuntimeError(f"Negative probe did not fail honestly: {label}")
            if label == "BUILD_FAILED" and not any(
                check["category"] == "build" and check["status"] == "FAIL"
                for check in verification["checks"]
            ):
                raise RuntimeError("Build failure was not detected")
            if label == "UNIT_FAILED_REGRESSION" and not any(
                case["status"] == "FAIL" for case in verification["cases"]
            ):
                raise RuntimeError("Behavior regression was not detected")
            if label == "STATIC_FAILED" and not any(
                check["category"] == "static" and check["status"] == "FAIL"
                for check in verification["checks"]
            ):
                raise RuntimeError("Type error was not detected")
            if label == "REVIEW_BLOCKED" and reviewer["status"] != "REJECTED":
                raise RuntimeError("Unsafe execution was not rejected")
            record = {
                "label": label,
                "scope": "Trusted controlled negative probe, not CodeWriter output or a job attempt",
                "verification": verification,
                "review": reviewer,
            }
            destination = folder / f"negative-{label.lower()}.json"
            destination.write_bytes(canonical(record))
            results.append(
                {
                    "label": label,
                    "file": str(destination.relative_to(ROOT)),
                    "sha256": digest(record),
                    "image_id": verification["image_id"],
                    "container_name": verification["container_name"],
                    "passed": False,
                    "review_status": reviewer["status"],
                }
            )
        (folder / "negative-summary.json").write_bytes(canonical(results))
        print(json.dumps(results, indent=2))
    except Exception:
        logger.exception("negative_sandbox.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
