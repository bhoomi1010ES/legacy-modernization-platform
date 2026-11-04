"""Read-only target adapter v2; observations only, never assertions or expected values."""

import importlib.util
import json
import logging
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

def main() -> None:
    try:
        request = json.load(sys.stdin)
        if set(request) != {"scenario", "inputs"}:
            raise ValueError("Unsupported request format")

        scenario = request["scenario"]
        inputs = request["inputs"]

        if scenario == "add":
            if set(inputs) != {"x", "y"} or any(
                type(value) is not int for value in inputs.values()
            ):
                raise ValueError("The approved contract accepts two integers")
            candidates = [
                path
                for path in [
                    Path("/work/modern/calc.py"),
                    *Path("/work/app/modules").glob("*/calc.py"),
                ]
                if path.is_file()
            ]
            if len(candidates) != 1:
                raise ValueError("Exactly one approved calculator target is required")
            path = candidates[0]
            spec = importlib.util.spec_from_file_location("acceptance_calc", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            result = module.add(inputs["x"], inputs["y"])
            json.dump(
                {"output": result, "side_effects": {"count": 1}},
                sys.stdout,
                allow_nan=False,
            )
            return

        # A fixture adapter can observe only its implemented application contract.
        # Frozen expected values must never be shipped to or read by this process.
        sys.stderr.write("UNOBSERVED: no approved application adapter implements this scenario\n")
        raise SystemExit(78)
    except Exception:
        logger.exception("target_adapter failed")
        raise


if __name__ == "__main__":
    main()
