"""Retrieval helpers that don't need a database."""

import pytest
from conftest import passage

from retrieval import STATEMENTS, normalize, within_budget, years_in

BALANCE, INCOME, CASH_FLOW = STATEMENTS


def test_company_names_match_regardless_of_punctuation():
    assert normalize("Coca-Cola's FY2021 margin") == "coca cola s fy2021 margin"
    assert normalize("Johnson & Johnson") == normalize("Johnson and Johnson")


def test_years_include_short_fiscal_years():
    assert years_in("FY2018 vs FY22 and Q2'23") == {2018, 2022, 2023}


@pytest.mark.parametrize(
    "question, statements",
    [
        ("What was capex in FY2018?", [CASH_FLOW]),
        ("Year-end inventory per the balance sheet?", [BALANCE]),
        ("DPO from accounts payable and COGS?", [BALANCE, INCOME]),
        ("Did AMD report customer concentration?", []),
    ],
)
def test_questions_route_to_the_statements_they_need(question, statements):
    assert [s for s in STATEMENTS if s.asked.search(question)] == statements


def test_budget_keeps_best_passages_first():
    big, too_big, small = passage("x" * 4000), passage("z" * 14000), passage("y" * 400)
    assert within_budget([big, too_big, small], budget=1200) == [big, small]


def test_budget_always_keeps_the_top_passage():
    assert len(within_budget([passage("x" * 40000)], budget=10)) == 1
