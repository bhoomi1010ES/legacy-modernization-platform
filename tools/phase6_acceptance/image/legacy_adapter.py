"""Read-only legacy adapter v1, using the same approved integer contract."""

import json
import logging
import sys

sys.path.insert(0, "/legacy")
from calc import add

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
        json.dump(
            {"output": add(inputs["x"], inputs["y"]), "side_effects": {"count": 1}},
            sys.stdout,
            allow_nan=False,
        )
    except Exception:
        logger.exception("legacy_adapter failed")
        raise


if __name__ == "__main__":
    main()
