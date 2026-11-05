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
    return {Decimal(m.replace(",", "")).normalize() for m in NUMBER.findall(text)}


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
    """Percent change takes [old, new]; ratio and percentage [part, whole]; difference [a, b] = a - b.

    Sum, average and product take two or more inputs.
    """
    if operation in ("sum", "average", "product"):
        if len(inputs) < 2:
            return None
        if operation == "product":
            return math.prod(inputs, start=Decimal(1))
        return sum(inputs) / (len(inputs) if operation == "average" else 1)
    if len(inputs) != 2:
        return None
    a, b = inputs
    if operation == "difference":
        return a - b
    if operation in ("ratio", "percentage"):
        if not b:
            return None
        return a / b * (100 if operation == "percentage" else 1)
    if operation == "percent_change":
        if not a:
            return None
        if (a < 0) == (b < 0):
            # Same sign: change in size, so capex going (1,373) -> (1,577) is growth.
            a, b = abs(a), abs(b)
        return (b - a) / abs(a) * 100
    return None


def format_result(result: Decimal, percent: bool, whole: bool, decimals: int) -> str:
    """Show a result with `decimals` places, but at least 3 significant digits (0.103, not 0.10).

    Whole results (e.g. a sum of whole numbers) have no decimals; percentages end in "%".
    """
    places = 0 if whole else decimals
    while not whole and 0 < abs(result) < Decimal(10) ** (2 - places):
        places += 1
    text = f"{result:,.{places}f}"
    return f"{text}%" if percent else text
