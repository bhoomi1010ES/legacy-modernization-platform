"""Real Docker probes, not a substitute for the human-gated model/job acceptance."""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.phase5 import Scenario  # noqa: E402 -- standalone backend bootstrap
from app.services.phase5_engine import replay  # noqa: E402
from app.services.phase6_sandbox import execute  # noqa: E402

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        cases = []
        legacy = []
        for index, inputs in enumerate(
            ({"x": 1, "y": 2}, {"x": -5, "y": 2}, {"x": 5, "y": -8}, {"x": 0, "y": 0})
        ):
            scenario = Scenario(
                name="add",
                module="calc",
                interface="add(x:int,y:int)->int",
                behavior="Integer addition",
                inputs=inputs,
            )
            first, second = await replay(scenario), await replay(scenario)
            if not first.get("available") or first != second:
                raise RuntimeError(
                    f'Legacy capture unavailable or non-reproducible: {first.get("reason", "observation mismatch")}'
                )
            legacy.append({"inputs": inputs, "first": first, "second": second})
            cases.append(
                {
                    "test_case_id": f"probe-{index}",
                    "name": "add",
                    "fixtures": inputs,
                    "expected": first["output"],
                    "side_effects": first["side_effects"],
                    "normalization": [],
                }
            )
        suite_hash = hashlib.sha256(
            json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        files = {
            "modern/calc.py": "def add(x: int, y: int) -> int:\n    return x + y\n"
        }
        result = await execute(files, cases, suite_hash)
        output = {
            "scope": "Real sandbox/adapter probe only. Not a G2-frozen job or real CodeWriter attempt.",
            "legacy_observations": legacy,
            "candidate_hash": suite_hash,
            "verification": result,
        }
        destination = ROOT / "artifacts/phase6-real-sandbox-probe.json"
        destination.write_text(
            json.dumps(output, sort_keys=True, indent=2), encoding="utf-8"
        )
        print(json.dumps(output, sort_keys=True, indent=2))
        if not result.get("available") or not result.get("passed"):
            raise RuntimeError(
                "Real sandbox probe failed; inspect saved command evidence"
            )
    except Exception:
        logger.exception("run_sandbox.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
