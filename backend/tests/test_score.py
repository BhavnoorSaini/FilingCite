"""The eval grader: Python marks numeric answers right or wrong."""

from decimal import Decimal

import pytest

from evals.score import grade


def record(expected: str, answer: str) -> dict:
    shown = {"answered": True, "answer": answer, "refusal": None, "citations": []}
    return {
        "expected": expected,
        "evidence": [],
        "retrieved": [],
        "top_similarity": 0.9,
        "on": shown,
        "off": shown,
    }


@pytest.mark.parametrize(
    "expected, answer, correct",
    [
        ("$1577.00", "Capex was $1,577 million.", True),
        ("$1577.00", "Capex was $1,600 million.", False),  # more than 1% off
        ("39.7%", "COGS was 0.397 of revenue.", True),  # ratio vs percentage
        ("$303.00", "Payables were $302,578 thousand.", True),  # thousands vs millions
    ],
)
def test_numeric_answers_within_one_percent(expected, answer, correct):
    assert grade(record(expected, answer), "on", Decimal("0.62"))["correct"] is correct


def test_written_answers_are_not_auto_graded():
    g = grade(record("Revenue grew because of strong data center sales.", "Yes."), "on", Decimal(0))
    assert not g["numeric"] and not g["correct"]
