"""Independent, image-owned tests: CodeWriter cannot alter these cases."""

import importlib.util
from pathlib import Path

import pytest

candidates = [
    path
    for path in [
        Path("/work/modern/calc.py"),
        *Path("/work/app/modules").glob("*/calc.py"),
    ]
    if path.is_file()
]
assert len(candidates) == 1, "Exactly one calculator target must exist"
spec = importlib.util.spec_from_file_location("independent_calc", candidates[0])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "x,y,expected",
    [
        (1, 2, 3),
        (-5, 2, -3),
        (5, -8, -3),
        (0, 0, 0),
        (123456, 100, 123556),
        (-10, -10, -20),
    ],
)
def test_integer_addition(x: int, y: int, expected: int) -> None:
    assert module.add(x, y) == expected
