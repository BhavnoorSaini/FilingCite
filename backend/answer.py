"""Question -> cited answer, or an honest refusal.

Python decides every refusal and does all arithmetic; the model only drafts the answer
from the passages it is given.
"""

import os
import re
from dataclasses import asdict
from decimal import Decimal

import psycopg
from pydantic import BaseModel, ValidationError

from figures import Operation, calculate, format_result, parse, values_in
from llm import Model, Reply, UsedNumber, build_prompt
from retrieval import Passage, search, years_in

REFUSAL_MESSAGES = {
    "weak_match": "Nothing in the loaded filings closely matches this question.",
    "not_in_filings": "The filings I found don't contain the answer.",
    "malformed_reply": "The answer couldn't be checked, so it isn't shown.",
    "invalid_citation": "The draft answer cited text it wasn't given, so it isn't shown.",
    "unverified_number": "The draft used a number I couldn't trace to the cited pages.",
}

PLACEHOLDER = re.compile(r"\{c(\d+)\}")
# A placeholder plus any "%" the model wrote after it: Python decides whether a result is
# a percentage, so a ratio of 0.103 is never shown as "0.103%".
PLACEHOLDER_IN_ANSWER = re.compile(r"\{c(\d+)\}(?:\s?%|\s+percent\b)?")
# Unit conversions may be calculation inputs: they change a traced figure's scale but
# can't invent its digits, and they show in the working.
UNIT_FACTORS = {100, 1000, 1000000}


class Citation(BaseModel):
    number: int
    company: str
    doc_name: str
    doc_type: str
    doc_period: int
    page: int
    doc_link: str | None


class CalculationResult(BaseModel):
    operation: Operation
    inputs: list[str]
    result: str


class AskResponse(BaseModel):
    answered: bool
    answer: str | None = None
    citations: list[Citation] = []
    calculations: list[CalculationResult] = []
    refusal: str | None = None  # a REFUSAL_MESSAGES key
    message: str | None = None


def refuse(reason: str) -> AskResponse:
    message = f"I don't know. {REFUSAL_MESSAGES[reason]}"
    return AskResponse(answered=False, refusal=reason, message=message)


def check_numbers(
    reply: Reply, used: list[UsedNumber], passages: list[Passage], question: str, verify: bool
) -> tuple[str, list[CalculationResult]] | str:
    """Every number must be on a cited page, or be computed here from numbers that are.

    Listed numbers and calculation inputs must be on the excerpt they name; inputs may
    also come from the question (like 365 in a formula the user defined) or be unit
    factors, as "excerpt 0". Numbers in the answer text must be on a cited page, be a
    computed result, or be a year the question mentions, so echoing a figure from a
    leading question doesn't pass. verify=False skips the tracing (still doing the
    arithmetic) so the eval can compare the number check off and on.
    """
    # The excerpt label (company, fiscal year) counts as part of its page: "3M", "2018".
    on_page = {
        i: values_in(f"{p.company} {p.content}") | {p.doc_period} for i, p in enumerate(passages, 1)
    }
    on_page[0] = values_in(question)

    for n in used:
        if PLACEHOLDER.fullmatch(n.value.strip()):
            continue  # an earlier result, checked below
        value = parse(n.value)
        if value is None or verify and abs(value) not in on_page[n.excerpt] | UNIT_FACTORS:
            return "unverified_number"

    results: list[tuple[Decimal, bool]] = []  # (value, is a percentage)
    shown: list[CalculationResult] = []
    for calc in reply.calculations:
        inputs: list[tuple[Decimal, bool]] = []
        for item in calc.inputs:
            earlier = PLACEHOLDER.fullmatch(item.value.strip())
            if not earlier:
                inputs.append((parse(item.value), False))
            elif 1 <= int(earlier[1]) <= len(results):
                inputs.append(results[int(earlier[1]) - 1])  # the exact earlier result
            else:
                return "malformed_reply"
        result = calculate(calc.operation, [value for value, _ in inputs])
        if result is None:
            return "malformed_reply"
        # Averages, sums and differences of percentages are percentages too.
        percent = calc.operation in ("percent_change", "percentage") or (
            calc.operation in ("average", "sum", "difference") and all(p for _, p in inputs)
        )
        results.append((result, percent))
        shown.append(
            CalculationResult(
                operation=calc.operation,
                inputs=[i.value for i in calc.inputs],
                result=format_result(result, percent, int(os.environ["CALC_DECIMALS"])),
            )
        )

    allowed = set().union(*(on_page[i] for i in reply.cited_excerpts), years_in(question))
    allowed |= set().union(*(values_in(c.result) for c in shown))
    if verify and not values_in(PLACEHOLDER.sub(" ", reply.answer)) <= allowed:
        return "unverified_number"
    if any(not 1 <= int(i) <= len(shown) for i in PLACEHOLDER.findall(reply.answer)):
        return "malformed_reply"
    return PLACEHOLDER_IN_ANSWER.sub(lambda m: shown[int(m[1]) - 1].result, reply.answer), shown


def respond(
    raw: str, passages: list[Passage], question: str, verify_numbers: bool = True
) -> AskResponse:
    """Check the model's raw reply and turn it into what the user sees."""
    try:
        reply = Reply.model_validate_json(raw)
    except ValidationError:
        return refuse("malformed_reply")
    if reply.status == "not_in_excerpts":
        return refuse("not_in_filings")
    if not reply.answer.strip() or not reply.cited_excerpts:
        return refuse("malformed_reply")
    cited = list(dict.fromkeys(reply.cited_excerpts))  # keep order, drop repeats
    used = reply.numbers + [n for c in reply.calculations for n in c.inputs]
    if not set(cited) <= set(range(1, len(passages) + 1)) or any(
        n.excerpt not in {0, *cited} for n in used
    ):
        return refuse("invalid_citation")

    checked = check_numbers(reply, used, passages, question, verify_numbers)
    if isinstance(checked, str):
        return refuse(checked)
    answer, calculations = checked
    citations = [Citation(number=i, **asdict(passages[n - 1])) for i, n in enumerate(cited, 1)]
    return AskResponse(answered=True, answer=answer, citations=citations, calculations=calculations)


def answer_question(conn: psycopg.Connection, question: str, model: Model) -> AskResponse:
    passages = search(conn, question, int(os.environ["RETRIEVAL_TOP_K"]))
    # Refuse when even the closest chunk in meaning is a weak match.
    if not passages or max(p.similarity for p in passages) < float(os.environ["MIN_SIMILARITY"]):
        return refuse("weak_match")
    return respond(model(build_prompt(question, passages)), passages, question)
