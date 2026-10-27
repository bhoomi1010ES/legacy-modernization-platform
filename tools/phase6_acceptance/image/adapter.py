"""Read-only target adapter v1; observations only, never assertions or expected values."""

import importlib.util
import json
import logging
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if set(request) != {"scenario", "inputs"} or request["scenario"] != "add":
            raise ValueError("Unsupported scenario")
        inputs = request["inputs"]
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
    except Exception:
        logger.exception("target_adapter failed")
        raise


if __name__ == "__main__":
    main()
