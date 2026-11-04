"""Question -> cited answer, or an honest refusal.

Python decides every refusal and does all arithmetic; the model only drafts the
answer from the passages it is given.
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

REFUSAL_MESSAGES: dict[str, str] = {
    "weak_match": "I don't know. Nothing in the loaded filings closely matches this question.",
    "not_in_filings": "I don't know. The filings I found don't contain the answer.",
    "malformed_reply": "I don't know. The answer couldn't be checked, so it isn't shown.",
    "invalid_citation": "I don't know. The draft answer cited text it wasn't given, so it isn't shown.",
    "unverified_number": (
        "I don't know. The draft answer used a number I couldn't trace to the cited pages, "
        "so it isn't shown."
    ),
}

PLACEHOLDER = re.compile(r"\{c(\d+)\}")


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
    answer: str | None
    citations: list[Citation]
    calculations: list[CalculationResult]
    refusal: RefusalReason | None
    message: str | None


def refuse(reason: RefusalReason) -> AskResponse:
    return AskResponse(
        answered=False,
        answer=None,
        citations=[],
        calculations=[],
        refusal=reason,
        message=REFUSAL_MESSAGES[reason],
    )


def check_reply(raw: str, passages: list[Passage]) -> Reply | RefusalReason:
    """Parse the model's reply and make sure it only cites excerpts it was given."""
    try:
        reply = Reply.model_validate_json(raw)
    except ValidationError:
        return "malformed_reply"
    if reply.status == "not_in_excerpts":
        return "not_in_filings"
    if not reply.answer.strip() or not reply.cited_excerpts:
        return "malformed_reply"

    given = set(range(1, len(passages) + 1))
    cited = set(reply.cited_excerpts)
    if not cited <= given or any(n.excerpt not in cited for n in reply.numbers):
        return "invalid_citation"
    return reply


def check_numbers(
    reply: Reply, passages: list[Passage], verify: bool = True
) -> tuple[str, list[CalculationResult]] | RefusalReason:
    """Every number must be on a cited page, or be computed here from numbers that are.

    Returns the answer with calculation results filled in. verify=False skips the
    traceability checks (still doing the arithmetic) so the eval can compare off vs on.
    """
    # The excerpt label (company, fiscal year) counts as part of the page, so "3M" and "2018" pass.
    on_page = {
        i: values_in(f"{p.company} {p.content}") | {Decimal(p.doc_period)}
        for i, p in enumerate(passages, 1)
    }
    cited = set(reply.cited_excerpts)

    def traceable(value: str, excerpt: int) -> bool:
        number = parse(value)
        if not verify:
            return number is not None
        return number is not None and abs(number).normalize() in on_page[excerpt]

    if not all(traceable(n.value, n.excerpt) for n in reply.numbers):
        return "unverified_number"

    decimals = int(os.environ["CALC_DECIMALS"])
    results: list[Decimal] = []
    shown: list[CalculationResult] = []
    for calc in reply.calculations:
        inputs = []
        for item in calc.inputs:
            earlier = PLACEHOLDER.fullmatch(item.value.strip())
            if earlier:  # the exact result of an earlier calculation
                index = int(earlier.group(1))
                if not 1 <= index <= len(results):
                    return "malformed_reply"
                inputs.append(results[index - 1])
            elif item.excerpt not in cited:
                return "invalid_citation"
            elif not traceable(item.value, item.excerpt):
                return "unverified_number"
            else:
                inputs.append(parse(item.value))
        result = calculate(calc.operation, inputs)
        if result is None:
            return "malformed_reply"
        results.append(result)
        shown.append(
            CalculationResult(
                operation=calc.operation,
                inputs=[i.value for i in calc.inputs],
                result=format_result(calc.operation, result, inputs, decimals),
            )
        )

    # Numbers written in the answer itself, ignoring the {c1} placeholders.
    cited_values = set().union(*(on_page[i] for i in cited))
    if verify and not values_in(PLACEHOLDER.sub(" ", reply.answer)) <= cited_values:
        return "unverified_number"
    if any(not 1 <= int(i) <= len(shown) for i in PLACEHOLDER.findall(reply.answer)):
        return "malformed_reply"
    answer = PLACEHOLDER.sub(lambda m: shown[int(m.group(1)) - 1].result, reply.answer)
    return answer, shown


def respond(raw: str, passages: list[Passage], verify_numbers: bool = True) -> AskResponse:
    """Turn the model's raw reply into the response the user sees."""
    reply = check_reply(raw, passages)
    if isinstance(reply, str):
        return refuse(reply)
    checked = check_numbers(reply, passages, verify_numbers)
    if isinstance(checked, str):
        return refuse(checked)
    answer, calculations = checked

    cited = list(dict.fromkeys(reply.cited_excerpts))  # keep order, drop repeats
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
    return AskResponse(
        answered=True,
        answer=answer,
        citations=citations,
        calculations=calculations,
        refusal=None,
        message=None,
    )


def answer_question(conn: psycopg.Connection, question: str, model: Model) -> AskResponse:
    passages = search(conn, question, int(os.environ["RETRIEVAL_TOP_K"]))
    if not passages or passages[0].similarity < float(os.environ["MIN_SIMILARITY"]):
        return refuse("weak_match")
    return respond(model(build_prompt(question, passages)), passages)
