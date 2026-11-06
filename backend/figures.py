"""Find numbers in text, and do the only math FilingCite allows.

Matching ignores formatting, sign and units ("$ 1,577", "(1,577)" and "1577" are the same),
but the digits must match exactly.
"""

import math
import re
from decimal import Decimal
from typing import Literal

Operation = Literal[
    "percent_change", "cagr", "percentage", "ratio", "difference", "sum", "average", "product"
]

# Labels, not figures: "10-K", "Q2", "2Q", "H1".
LABELS = re.compile(r"\b(?:10-K|10-Q|8-K|Q[1-4]|[1-4]Q|H[12])\b", re.IGNORECASE)
# "FY22", "2Q23" and "Q2'23" are read as full years.
SHORT_FISCAL_YEAR = re.compile(r"\b(?:FY|Q[1-4]|[1-4]Q)\s?'?(\d{2})\b", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
# Models often write Unicode dashes and minus signs; treat them as "-".
DASHES = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-"))


def values_in(text: str) -> set[Decimal]:
    """Every number written in the text, as an absolute value."""
    text = LABELS.sub(" ", SHORT_FISCAL_YEAR.sub(r" 20\1", text.translate(DASHES)))
    return {Decimal(m.replace(",", "")) for m in NUMBER.findall(text)}


def parse(value: str) -> Decimal | None:
    """Read one number as the model copied it, e.g. "$1,577", "(1,577)", "-3.2%"."""
    value = value.translate(DASHES)
    match = NUMBER.search(value)
    if not match:
        return None
    number = Decimal(match.group().replace(",", ""))
    negative = "(" in value[: match.start()] or "-" in value[: match.start()]
    return -number if negative else number


def calculate(operation: Operation, inputs: list[Decimal]) -> Decimal | None:
    """Do one calculation, or return None if its inputs don't fit it."""
    match operation, inputs:
        case "sum", [_, _, *_]:
            return sum(inputs)
        case "average", [_, _, *_]:
            return sum(inputs) / len(inputs)
        case "product", [_, _, *_]:
            return math.prod(inputs)
        case "difference", [a, b]:
            return a - b
        case "ratio", [part, whole] if whole:
            return part / whole
        case "percentage", [part, whole] if whole:
            return part / whole * 100
        case "percent_change", [old, new] if old:
            if (old < 0) == (new < 0):
                # Same sign: change in size, so capex going (1,373) -> (1,577) is growth.
                old, new = abs(old), abs(new)
            return (new - old) / abs(old) * 100
        case "cagr", [start, end, years] if start > 0 and end > 0 and years > 0:
            return ((end / start) ** (1 / years) - 1) * 100
    return None


def format_result(result: Decimal, percent: bool, decimals: int, exact: bool = False) -> str:
    """Format a result to `decimals` places, with "%" for percentages.

    Whole numbers get no decimals. Unless `exact` (the question asked for this rounding),
    small results keep 3 significant digits (0.103, not 0.10).
    """
    if result == result.to_integral_value():
        places = 0
    else:
        places = decimals
        while not exact and abs(result) < Decimal(10) ** (2 - places):
            places += 1
    text = f"{result:,.{places}f}"
    return f"{text}%" if percent else text
