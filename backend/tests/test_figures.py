from decimal import Decimal as D

import pytest

from figures import calculate, format_result, parse, values_in


def test_values_ignore_formatting_and_sign():
    assert values_in("$ 1,577 and (1,373) and 2.5%") == {D(1577), D(1373), D("2.5")}


@pytest.mark.parametrize(
    "text, value",
    [("$1,577", D(1577)), ("(1,577)", D(-1577)), ("−3.2%", D("-3.2")), ("n/a", None)],
)
def test_parse(text, value):
    assert parse(text) == value


@pytest.mark.parametrize(
    "operation, inputs, result",
    [
        ("sum", [D(1), D(2), D(3)], D(6)),
        ("average", [D(1500), D(1601)], D("1550.5")),
        ("product", [D(365), D("0.25")], D("91.25")),
        ("difference", [D(10), D(4)], D(6)),
        ("ratio", [D(1), D(4)], D("0.25")),
        ("percentage", [D(1), D(4)], D(25)),
        ("percent_change", [D(100), D(110)], D(10)),
        # Outflows shown in parentheses: (100) -> (110) is still 10% growth.
        ("percent_change", [D(-100), D(-110)], D(10)),
        ("cagr", [D(100), D(121), D(2)], D(10)),
        ("ratio", [D(1), D(0)], None),
        ("sum", [D(1)], None),
    ],
)
def test_calculate(operation, inputs, result):
    assert calculate(operation, inputs) == result


def test_format_result():
    assert format_result(D("0.10283"), percent=False, decimals=2) == "0.103"
    assert format_result(D("10.283"), percent=True, decimals=2) == "10.28%"
    assert format_result(D(25385), percent=False, decimals=2) == "25,385"
