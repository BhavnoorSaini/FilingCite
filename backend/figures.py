"""Find numbers in text and do the only arithmetic FilingCite allows.

Matching ignores formatting ("$ 1,577", "(1,577)", "1577" are the same value),
sign (filings show outflows in parentheses) and units. Digits must match exactly:
"1.6" never matches "1,577".
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal

Operation = Literal["percent_change", "ratio", "difference", "sum"]

# Labels, not figures: document names ("10-K") and quarters or halves ("Q2", "2Q", "H1").
LABELS = re.compile(r"\b(?:10-K|10-Q|8-K|Q[1-4]|[1-4]Q|H[12])\b", re.IGNORECASE)
# "FY22" and "2Q23" / "Q2'23" mean 2022 and 2023, so they are checked as those years.
SHORT_FISCAL_YEAR = re.compile(r"\b(?:FY|Q[1-4]|[1-4]Q)\s?'?(\d{2})\b", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def values_in(text: str) -> set[Decimal]:
    """Every number written in the text, as an absolute value."""
    text = LABELS.sub(" ", SHORT_FISCAL_YEAR.sub(r" 20\1", text))
    return {Decimal(m.replace(",", "")).normalize() for m in NUMBER.findall(text)}


def parse(value: str) -> Decimal | None:
    """Read one number as the model copied it, e.g. "$1,577", "(1,577)", "-3.2%"."""
    match = NUMBER.search(value)
    if not match:
        return None
    try:
        number = Decimal(match.group().replace(",", ""))
    except InvalidOperation:
        return None
    negative = "(" in value[: match.start()] or "-" in value[: match.start()]
    return -number if negative else number


def calculate(operation: Operation, inputs: list[Decimal]) -> Decimal | None:
    """Percent change takes [old, new]; ratio [numerator, denominator]; difference [a, b] = a - b."""
    if operation == "sum":
        return sum(inputs, Decimal(0)) if len(inputs) >= 2 else None
    if len(inputs) != 2:
        return None
    a, b = inputs
    if operation == "difference":
        return a - b
    if operation == "ratio":
        return a / b if b else None
    if operation == "percent_change":
        if not a:
            return None
        if (a < 0) == (b < 0):
            # Same sign: change in size, so capex going (1,373) -> (1,577) is growth.
            a, b = abs(a), abs(b)
        return (b - a) / abs(a) * 100
    return None


def format_result(
    operation: Operation, result: Decimal, inputs: list[Decimal], decimals: int
) -> str:
    if operation == "percent_change":
        return f"{result:.{decimals}f}%"
    if operation == "ratio":
        return f"{result:.{decimals}f}"
    # Sums and differences of whole numbers stay whole.
    places = 0 if all(x == x.to_integral_value() for x in inputs) else decimals
    return f"{result:,.{places}f}"
