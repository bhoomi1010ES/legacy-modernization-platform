"""Legacy integer calculator; modernize without changing its integer contract."""


def add(x: int, y: int) -> int:
    result = x
    direction = 1 if y >= 0 else -1
    for _ in range(abs(y)):
        result += direction
    return result
