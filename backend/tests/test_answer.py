"""The number check, citations and refusals, with a fake model."""

from conftest import BALANCE, INCOME, PASSAGES, passage, reply

import answer
from answer import answer_question, respond

QUESTION = "What was Amazon's FY2018 cost of sales?"


def test_quoted_figure_is_answered_with_citations():
    r = respond(
        reply("Cost of sales was $139,156 million in 2018.", numbers=[("139,156", 1)]),
        PASSAGES,
        QUESTION,
    )
    assert r.answered and r.answer == "Cost of sales was $139,156 million in 2018."
    [citation] = r.citations
    assert (citation.number, citation.doc_name, citation.page) == (1, "AMAZON_2018_10K", 38)


def test_citations_are_numbered_in_order_without_repeats():
    r = respond(reply("Total assets were $162,648 million.", cited=[2, 1, 2]), PASSAGES, QUESTION)
    assert [(c.number, c.page) for c in r.citations] == [(1, 40), (2, 38)]


def test_python_does_the_arithmetic():
    r = respond(
        reply(
            "Gross margin was {c1}.",
            calculations=[("percentage", [("139,156", 1), ("232,887", 1)])],
        ),
        PASSAGES,
        QUESTION,
    )
    assert r.answer == "Gross margin was 59.75%."
    assert r.calculations[0].inputs == ["139,156", "232,887"]


def test_chained_calculation_with_a_number_from_the_question():
    question = "What is DPO? DPO = 365 * average accounts payable / cost of sales."
    r = respond(
        reply(
            "DPO was {c3} days.",
            cited=[1, 2],
            calculations=[
                ("average", [("38,192", 2), ("34,616", 2)]),
                ("ratio", [("{c1}", 0), ("139,156", 1)]),
                ("product", [("365", 0), ("{c2}", 0)]),
            ],
        ),
        PASSAGES,
        question,
    )
    assert r.answer == "DPO was 95.49 days."


def test_copied_result_counts_as_that_result():
    r = respond(
        reply(
            "The average was {c3}.",
            calculations=[
                ("sum", [("139,156", 1), ("232,887", 1)]),
                ("percentage", [("372,043", 0), ("232,887", 1)]),
                ("average", [("{c2}", 0), ("139,156", 1)]),
            ],
        ),
        PASSAGES,
        QUESTION,
    )
    assert r.answered and r.calculations[1].inputs == ["{c1}", "232,887"]


def test_unused_result_is_refused():
    r = respond(
        reply(
            "Gross margin was {c1}.",
            calculations=[
                ("percentage", [("139,156", 1), ("232,887", 1)]),
                ("sum", [("139,156", 1), ("232,887", 1)]),
            ],
        ),
        PASSAGES,
        QUESTION,
    )
    assert r.refusal == "malformed_reply"


def test_result_written_out_in_the_answer_counts_as_used():
    r = respond(
        reply(
            "Together they were 372,043.",
            calculations=[("sum", [("139,156", 1), ("232,887", 1)])],
        ),
        PASSAGES,
        QUESTION,
    )
    assert r.answered


def test_rounding_the_question_asks_for():
    r = respond(
        reply(
            "Gross margin was {c1}.",
            calculations=[("percentage", [("139,156", 1), ("232,887", 1)])],
            round_to=1,
        ),
        PASSAGES,
        "What was Amazon's FY2018 gross margin? Round to one decimal place.",
    )
    assert r.answer == "Gross margin was 59.8%."


def test_number_from_the_question_under_another_excerpt():
    question = "What is Amazon's 2 year growth rate?"
    r = respond(
        reply(
            "Over 2 years it grew {c1} a year.",
            calculations=[("cagr", [("111,934", 1), ("139,156", 1), ("2", 1)])],
        ),
        PASSAGES,
        question,
    )
    assert r.answer == "Over 2 years it grew 11.50% a year."


def test_ratio_never_shown_as_a_percentage():
    r = respond(
        reply("The ratio was {c1}%.", calculations=[("ratio", [("139,156", 1), ("232,887", 1)])]),
        PASSAGES,
        QUESTION,
    )
    assert r.answer == "The ratio was 0.598."


def test_unit_conversion_is_allowed():
    r = respond(
        reply("That is ${c1} billion.", calculations=[("ratio", [("139,156", 1), ("1,000", 1)])]),
        PASSAGES,
        QUESTION,
    )
    assert r.answer == "That is $139.16 billion."


def test_unit_conversion_by_multiplying():
    r = respond(
        reply("That is ${c1} billion.", calculations=[("product", [("139,156", 1), ("0.001", 1)])]),
        PASSAGES,
        QUESTION,
    )
    assert r.answer == "That is $139.16 billion."


def test_invented_number_is_blocked():
    r = respond(reply("Cost of sales was $150,000 million."), PASSAGES, QUESTION)
    assert r.refusal == "unverified_number" and not r.answered


def test_rounded_number_is_blocked():
    r = respond(reply("Cost of sales was about $139 billion."), PASSAGES, QUESTION)
    assert r.refusal == "unverified_number"


def test_figure_echoed_from_a_leading_question_is_blocked():
    question = "Did Amazon's cost of sales reach $150,000 million in 2018?"
    r = respond(reply("Yes, $150,000 million.", numbers=[("150,000", 0)]), PASSAGES, question)
    assert r.refusal == "unverified_number"


def test_calculation_input_not_on_its_page_is_blocked():
    r = respond(
        reply("Margin was {c1}.", calculations=[("percentage", [("120,000", 1), ("232,887", 1)])]),
        PASSAGES,
        QUESTION,
    )
    assert r.refusal == "unverified_number"


def test_number_check_off_lets_invented_numbers_through():
    r = respond(
        reply("Cost of sales was $150,000 million."), PASSAGES, QUESTION, verify_numbers=False
    )
    assert r.answered


def test_citing_an_excerpt_it_was_not_given():
    r = respond(reply("Cost of sales was $139,156 million.", cited=[1, 9]), PASSAGES, QUESTION)
    assert r.refusal == "invalid_citation"


def test_number_from_an_uncited_excerpt():
    r = respond(
        reply("Total assets were $162,648 million.", numbers=[("162,648", 2)]), PASSAGES, QUESTION
    )
    assert r.refusal == "invalid_citation"


def test_model_says_the_excerpts_lack_the_answer():
    r = respond(reply(cited=[], status="not_in_excerpts"), PASSAGES, QUESTION)
    assert r.refusal == "not_in_filings" and r.message.startswith("I don't know")


def test_malformed_replies_are_refused():
    assert respond("not json", PASSAGES, QUESTION).refusal == "malformed_reply"
    assert respond(reply("An answer with no citations.", cited=[]), PASSAGES, QUESTION).refusal == (
        "malformed_reply"
    )
    bad_placeholder = reply(
        "Margin {c2}.", calculations=[("ratio", [("139,156", 1), ("232,887", 1)])]
    )
    assert respond(bad_placeholder, PASSAGES, QUESTION).refusal == "malformed_reply"


def test_weak_match_refuses_without_calling_the_model(monkeypatch):
    monkeypatch.setattr(answer, "search", lambda conn, q, k: [passage("pizza", similarity=0.4)])

    def model(prompt):
        raise AssertionError("the model must not be called")

    r = answer_question(None, "Give me a pizza recipe.", model)
    assert r.refusal == "weak_match"


def test_strong_match_sends_the_excerpts_to_the_model(monkeypatch):
    monkeypatch.setattr(answer, "search", lambda conn, q, k: [INCOME, BALANCE])
    prompts = []

    def model(prompt):
        prompts.append(prompt)
        return reply("Cost of sales was $139,156 million.")

    assert answer_question(None, QUESTION, model).answered
    assert "[Excerpt 2] Amazon 10K 2018, page 40" in prompts[0]
