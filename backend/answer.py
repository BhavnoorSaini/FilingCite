"""Question -> cited answer, or an honest refusal.

Python decides every refusal; the model only drafts the answer from the passages it is given.
"""

import os
from typing import Literal

import psycopg
from pydantic import BaseModel, ValidationError

from llm import Model, Reply, build_prompt
from retrieval import Passage, search

RefusalReason = Literal["weak_match", "not_in_filings", "malformed_reply", "invalid_citation"]

REFUSAL_MESSAGES: dict[str, str] = {
    "weak_match": "I don't know. Nothing in the loaded filings closely matches this question.",
    "not_in_filings": "I don't know. The filings I found don't contain the answer.",
    "malformed_reply": "I don't know. The answer couldn't be checked, so it isn't shown.",
    "invalid_citation": "I don't know. The draft answer cited text it wasn't given, so it isn't shown.",
}


class Citation(BaseModel):
    number: int
    company: str
    doc_name: str
    doc_type: str
    doc_period: int
    page: int
    doc_link: str | None


class AskResponse(BaseModel):
    answered: bool
    answer: str | None
    citations: list[Citation]
    refusal: RefusalReason | None
    message: str | None


def refuse(reason: RefusalReason) -> AskResponse:
    return AskResponse(
        answered=False,
        answer=None,
        citations=[],
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


def answer_question(conn: psycopg.Connection, question: str, model: Model) -> AskResponse:
    passages = search(conn, question, int(os.environ["RETRIEVAL_TOP_K"]))
    if not passages or passages[0].similarity < float(os.environ["MIN_SIMILARITY"]):
        return refuse("weak_match")

    checked = check_reply(model(build_prompt(question, passages)), passages)
    if isinstance(checked, str):
        return refuse(checked)

    cited = list(dict.fromkeys(checked.cited_excerpts))  # keep order, drop repeats
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
        answered=True, answer=checked.answer, citations=citations, refusal=None, message=None
    )
