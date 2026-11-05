"""Find numbers in text and do the only arithmetic FilingCite allows.

Matching ignores formatting ("$ 1,577", "(1,577)", "1577" are the same value),
sign (filings show outflows in parentheses) and units. Digits must match exactly:
"1.6" never matches "1,577".
"""

import math
import re
from decimal import Decimal
from typing import Literal

Operation = Literal[
    "percent_change", "percentage", "ratio", "difference", "sum", "average", "product"
]

# Labels, not figures: document names ("10-K") and quarters or halves ("Q2", "2Q", "H1").
LABELS = re.compile(r"\b(?:10-K|10-Q|8-K|Q[1-4]|[1-4]Q|H[12])\b", re.IGNORECASE)
# "FY22" and "2Q23" / "Q2'23" mean 2022 and 2023, so they are checked as those years.
SHORT_FISCAL_YEAR = re.compile(r"\b(?:FY|Q[1-4]|[1-4]Q)\s?'?(\d{2})\b", re.IGNORECASE)
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
# Models often write Unicode hyphens and minus signs ("10\u2011K", "\u22123.2"); read them as "-".
DASHES = str.maketrans({c: "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})


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
    if operation in ("sum", "average", "product"):
        if len(inputs) < 2:
            return None
    elif len(inputs) != 2:
        return None

    match operation:
        case "sum":
            return sum(inputs)
        case "average":
            return sum(inputs) / len(inputs)
        case "product":
            return math.prod(inputs)
        case "difference":
            a, b = inputs
            return a - b
        case "ratio" | "percentage":
            part, whole = inputs
            if not whole:
                return None
            return part / whole * (100 if operation == "percentage" else 1)
        case "percent_change":
            old, new = inputs
            if not old:
                return None
            if (old < 0) == (new < 0):
                # Same sign: change in size, so capex going (1,373) -> (1,577) is growth.
                old, new = abs(old), abs(new)
            return (new - old) / abs(old) * 100
    return None


def format_result(result: Decimal, percent: bool, decimals: int) -> str:
    """Show a result with `decimals` places, but at least 3 significant digits (0.103, not 0.10).

    Whole results (e.g. a sum of whole numbers) have no decimals; percentages end in "%".
    """
    whole = result == result.to_integral_value()
    places = 0 if whole else decimals
    while not whole and abs(result) < Decimal(10) ** (2 - places):
        places += 1
    text = f"{result:,.{places}f}"
    return f"{text}%" if percent else text
