"""Turn a question into a cited answer, or refuse.

The model drafts; Python checks the reply and does all the math.
"""

import os
import re
from dataclasses import asdict
from decimal import Decimal

import psycopg
from pydantic import BaseModel, ValidationError

from figures import Operation, calculate, format_result, parse, values_in
from llm import Calculation, Model, Reply, build_prompt
from retrieval import Passage, search

REFUSAL_MESSAGES = {
    "weak_match": "Nothing in the loaded filings closely matches this question.",
    "not_in_filings": "The filings I found don't contain the answer.",
    "malformed_reply": "The answer couldn't be checked, so it isn't shown.",
    "invalid_citation": "The draft answer cited text it wasn't given, so it isn't shown.",
}

PLACEHOLDER = re.compile(r"\{c(\d+)\}")
# Drops any "%" the model put after a placeholder: Python decides what's a percentage.
PLACEHOLDER_IN_ANSWER = re.compile(r"\{c(\d+)\}(?:\s?%|\s+percent\b)?")


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


def earlier_result(value: str, shown: list[CalculationResult]) -> int | None:
    """Which earlier result an input means: "{c1}", or a copy of that result ("31,555")."""
    placeholder = PLACEHOLDER.fullmatch(value.strip())
    if placeholder:
        return int(placeholder[1])
    return next((i for i, c in enumerate(shown, 1) if parse(c.result) == parse(value)), None)


def run_calculations(
    calculations: list[Calculation], round_to: int | None
) -> list[CalculationResult] | None:
    """Run the model's calculations in order, or return None if one can't be done.

    Earlier results are reused at full precision, not as rounded for display.
    """
    decimals = int(os.environ["CALC_DECIMALS"]) if round_to is None else round_to
    results: list[tuple[Decimal, bool]] = []  # (value, is a percentage)
    shown: list[CalculationResult] = []
    for calc in calculations:
        inputs: list[tuple[Decimal, bool]] = []
        written: list[str] = []
        for value in calc.inputs:
            n = earlier_result(value, shown)
            if n is None:
                number = parse(value)
                if number is None:
                    return None
                inputs.append((number, False))
                written.append(value)
            elif 1 <= n <= len(results):
                inputs.append(results[n - 1])
                written.append(f"{{c{n}}}")
            else:
                return None
        result = calculate(calc.operation, [value for value, _ in inputs])
        if result is None:
            return None
        # Averages, sums and differences of percentages are percentages too.
        percent = calc.operation in ("percent_change", "cagr", "percentage") or (
            calc.operation in ("average", "sum", "difference") and all(p for _, p in inputs)
        )
        results.append((result, percent))
        shown.append(
            CalculationResult(
                operation=calc.operation,
                inputs=written,
                result=format_result(result, percent, decimals, exact=round_to is not None),
            )
        )
    return shown


def all_results_used(answer: str, calculations: list[CalculationResult]) -> bool:
    """True if every result is in the answer or feeds a later calculation.

    An unused result means the model lost track of its numbering.
    """
    in_answer = values_in(PLACEHOLDER.sub(" ", answer))
    used = {int(n) for n in PLACEHOLDER.findall(answer)}
    used |= {int(n) for c in calculations for i in c.inputs for n in PLACEHOLDER.findall(i)}
    used |= {i for i, c in enumerate(calculations, 1) if values_in(c.result) <= in_answer}
    return used == set(range(1, len(calculations) + 1))


def respond(raw: str, passages: list[Passage]) -> AskResponse:
    """Check the model's reply and build what the user sees."""
    try:
        reply = Reply.model_validate_json(raw)
    except ValidationError:
        return refuse("malformed_reply")
    if reply.status == "not_in_excerpts":
        return refuse("not_in_filings")
    cited = list(dict.fromkeys(reply.cited_excerpts))  # keep order, drop repeats
    if not reply.answer.strip() or not cited:
        return refuse("malformed_reply")
    if not set(cited) <= set(range(1, len(passages) + 1)):
        return refuse("invalid_citation")

    calculations = run_calculations(reply.calculations, reply.round_to)
    if calculations is None or not all_results_used(reply.answer, calculations):
        return refuse("malformed_reply")

    answer = PLACEHOLDER_IN_ANSWER.sub(lambda m: calculations[int(m[1]) - 1].result, reply.answer)
    citations = [Citation(number=i, **asdict(passages[n - 1])) for i, n in enumerate(cited, 1)]
    return AskResponse(answered=True, answer=answer, citations=citations, calculations=calculations)


def answer_question(conn: psycopg.Connection, question: str, model: Model) -> AskResponse:
    passages = search(conn, question, int(os.environ["RETRIEVAL_TOP_K"]))
    # Refuse if even the best match is weak.
    if not passages or max(p.similarity for p in passages) < float(os.environ["MIN_SIMILARITY"]):
        return refuse("weak_match")
    return respond(model(build_prompt(question, passages)), passages)
