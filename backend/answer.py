"""Question -> cited answer, or an honest refusal.

Python decides every refusal and does all arithmetic; the model only drafts the answer
from the passages it is given.
"""

import os
import re
from decimal import Decimal
from typing import Literal

import psycopg
from pydantic import BaseModel, ValidationError

from figures import Operation, calculate, format_result, parse, values_in
from llm import Model, Reply, build_prompt
from retrieval import Passage, search

RefusalReason = Literal[
    "weak_match", "not_in_filings", "malformed_reply", "invalid_citation", "unverified_number"
]
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
UNIT_FACTORS = {Decimal(100), Decimal(1000), Decimal(1000000)}


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
    refusal: RefusalReason | None = None
    message: str | None = None


def refuse(reason: RefusalReason) -> AskResponse:
    message = f"I don't know. {REFUSAL_MESSAGES[reason]}"
    return AskResponse(answered=False, refusal=reason, message=message)


def check_numbers(
    reply: Reply, passages: list[Passage], question: str, verify: bool
) -> tuple[str, list[CalculationResult]] | RefusalReason:
    """Every number must be on a cited page, or be computed here from numbers that are.

    Calculation inputs may also come from the question (like 365 in a formula the user
    defined) or be unit factors, as "excerpt 0". Numbers in the answer text must be on a
    cited page, be a computed result, or be a year the question mentions, so echoing a
    figure from a leading question doesn't pass. verify=False skips the tracing (still doing
    the arithmetic) so the eval can compare the number check off and on.
    """
    # The excerpt label (company, fiscal year) counts as part of its page: "3M", "2018".
    on_page = {
        i: values_in(f"{p.company} {p.content}") | {Decimal(p.doc_period)}
        for i, p in enumerate(passages, 1)
    }
    on_page[0] = values_in(question)

    def traced(value: str, excerpt: int) -> bool:
        number = parse(value)
        known = on_page.get(excerpt, set()) | UNIT_FACTORS
        return number is not None and (not verify or abs(number).normalize() in known)

    if not all(traced(n.value, n.excerpt) for n in reply.numbers):
        return "unverified_number"

    results: list[tuple[Decimal, bool]] = []  # (value, is a percentage)
    shown: list[CalculationResult] = []
    for calc in reply.calculations:
        inputs: list[tuple[Decimal, bool]] = []
        for item in calc.inputs:
            earlier = PLACEHOLDER.fullmatch(item.value.strip())
            if earlier:  # the exact result of an earlier calculation
                if not 1 <= int(earlier[1]) <= len(results):
                    return "malformed_reply"
                inputs.append(results[int(earlier[1]) - 1])
            elif item.excerpt not in {0, *reply.cited_excerpts}:
                return "invalid_citation"
            elif not traced(item.value, item.excerpt):
                return "unverified_number"
            else:
                inputs.append((parse(item.value), False))
        result = calculate(calc.operation, [value for value, _ in inputs])
        if result is None:
            return "malformed_reply"
        # Averages, sums and differences of percentages are percentages too.
        percent = calc.operation in ("percent_change", "percentage") or (
            calc.operation in ("average", "sum", "difference") and all(p for _, p in inputs)
        )
        whole = not percent and calc.operation != "ratio" and result == result.to_integral_value()
        results.append((result, percent))
        shown.append(
            CalculationResult(
                operation=calc.operation,
                inputs=[i.value for i in calc.inputs],
                result=format_result(result, percent, whole, int(os.environ["CALC_DECIMALS"])),
            )
        )

    allowed = set().union(*(on_page[i] for i in reply.cited_excerpts))
    allowed |= {y for y in on_page[0] if y == y.to_integral_value() and 1900 <= y <= 2100}
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
    if not set(cited) <= set(range(1, len(passages) + 1)) or any(
        n.excerpt not in {0, *cited} for n in reply.numbers
    ):
        return refuse("invalid_citation")

    checked = check_numbers(reply, passages, question, verify_numbers)
    if isinstance(checked, str):
        return refuse(checked)
    answer, calculations = checked
    citations = [
        Citation(
            number=i,
            company=p.company,
            doc_name=p.doc_name,
            doc_type=p.doc_type,
            doc_period=p.doc_period,
            page=p.page,
            doc_link=p.doc_link,
        )
        for i, p in enumerate((passages[n - 1] for n in cited), 1)
    ]
    return AskResponse(answered=True, answer=answer, citations=citations, calculations=calculations)


def answer_question(conn: psycopg.Connection, question: str, model: Model) -> AskResponse:
    passages = search(conn, question, int(os.environ["RETRIEVAL_TOP_K"]))
    # Refuse when even the closest chunk in meaning is a weak match.
    if not passages or max(p.similarity for p in passages) < float(os.environ["MIN_SIMILARITY"]):
        return refuse("weak_match")
    return respond(model(build_prompt(question, passages)), passages, question)
