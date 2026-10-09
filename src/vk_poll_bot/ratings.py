from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation


def valid_rating(value) -> bool:
    return (type(value) in {int, float} and math.isfinite(value)
            and 1 <= value <= 10 and value * 2 == int(value * 2))


def parse_rating(text: str) -> int | float:
    try:
        number = Decimal(text.strip().replace(",", "."))
        if not number.is_finite() or not 1 <= number <= 10 or number * 2 != int(number * 2):
            raise ValueError
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError("Рейтинг от 1 до 10 с шагом 0,5 (например, 6 или 6,5)") from None
    return int(number) if number == int(number) else float(number)


def format_rating(value: int | float) -> str:
    return f"{value:g}".replace(".", ",")
