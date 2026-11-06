"""Answers, calculations, citations and refusals, with a fake model."""

import pytest
from conftest import BALANCE, INCOME, PASSAGES, passage, reply

import answer
from answer import answer_question, respond

QUESTION = "What was Amazon's FY2018 cost of sales?"


def test_answer_with_citations():
    r = respond(reply("Cost of sales was $139,156 million in 2018."), PASSAGES)
    assert r.answered and r.answer == "Cost of sales was $139,156 million in 2018."
    [citation] = r.citations
    assert (citation.number, citation.doc_name, citation.page) == (1, "AMAZON_2018_10K", 38)


def test_citations_are_numbered_in_order_without_repeats():
    r = respond(reply("Total assets were $162,648 million.", cited=[2, 1, 2]), PASSAGES)
    assert [(c.number, c.page) for c in r.citations] == [(1, 40), (2, 38)]


def test_python_does_the_arithmetic():
    r = respond(
        reply("Gross margin was {c1}.", calculations=[("percentage", ["139,156", "232,887"])]),
        PASSAGES,
    )
    assert r.answer == "Gross margin was 59.75%."
    assert r.calculations[0].inputs == ["139,156", "232,887"]


def test_chained_calculation():
    r = respond(
        reply(
            "DPO was {c3} days.",
            cited=[1, 2],
            calculations=[
                ("average", ["38,192", "34,616"]),
                ("ratio", ["{c1}", "139,156"]),
                ("product", ["365", "{c2}"]),
            ],
        ),
        PASSAGES,
    )
    assert r.answer == "DPO was 95.49 days."


def test_copied_result_counts_as_that_result():
    r = respond(
        reply(
            "The average was {c3}.",
            calculations=[
                ("sum", ["139,156", "232,887"]),
                ("percentage", ["372,043", "232,887"]),
                ("average", ["{c2}", "139,156"]),
            ],
        ),
        PASSAGES,
    )
    assert r.answered and r.calculations[1].inputs == ["{c1}", "232,887"]


def test_unused_result_is_refused():
    r = respond(
        reply(
            "Gross margin was {c1}.",
            calculations=[
                ("percentage", ["139,156", "232,887"]),
                ("sum", ["139,156", "232,887"]),
            ],
        ),
        PASSAGES,
    )
    assert r.refusal == "malformed_reply"


def test_result_written_out_in_the_answer_counts_as_used():
    r = respond(
        reply("Together they were 372,043.", calculations=[("sum", ["139,156", "232,887"])]),
        PASSAGES,
    )
    assert r.answered


def test_rounding_the_question_asks_for():
    r = respond(
        reply(
            "Gross margin was {c1}.",
            calculations=[("percentage", ["139,156", "232,887"])],
            round_to=1,
        ),
        PASSAGES,
    )
    assert r.answer == "Gross margin was 59.8%."


def test_ratio_never_shown_as_a_percentage():
    r = respond(
        reply("The ratio was {c1}%.", calculations=[("ratio", ["139,156", "232,887"])]),
        PASSAGES,
    )
    assert r.answer == "The ratio was 0.598."


@pytest.mark.parametrize("operation, factor", [("ratio", "1,000"), ("product", "0.001")])
def test_unit_conversion(operation, factor):
    r = respond(
        reply("That is ${c1} billion.", calculations=[(operation, ["139,156", factor])]),
        PASSAGES,
    )
    assert r.answer == "That is $139.16 billion."


def test_citing_an_excerpt_it_was_not_given():
    r = respond(reply("Cost of sales was $139,156 million.", cited=[1, 9]), PASSAGES)
    assert r.refusal == "invalid_citation"


def test_model_says_the_excerpts_lack_the_answer():
    r = respond(reply(cited=[], status="not_in_excerpts"), PASSAGES)
    assert r.refusal == "not_in_filings" and r.message.startswith("I don't know")


def test_malformed_replies_are_refused():
    assert respond("not json", PASSAGES).refusal == "malformed_reply"
    no_citations = reply("An answer with no citations.", cited=[])
    assert respond(no_citations, PASSAGES).refusal == "malformed_reply"
    bad_placeholder = reply("Margin {c2}.", calculations=[("ratio", ["139,156", "232,887"])])
    assert respond(bad_placeholder, PASSAGES).refusal == "malformed_reply"
    not_a_number = reply("Margin {c1}.", calculations=[("ratio", ["n/a", "232,887"])])
    assert respond(not_a_number, PASSAGES).refusal == "malformed_reply"


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
