"""Shared test helpers. No test calls a real model, database or API."""

import json

import pytest

from retrieval import Passage


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    for key, value in {
        "CALC_DECIMALS": "2",
        "MIN_SIMILARITY": "0.62",
        "RETRIEVAL_TOP_K": "10",
    }.items():
        monkeypatch.setenv(key, value)


def passage(content: str, page: int = 40, similarity: float = 0.8) -> Passage:
    return Passage(
        doc_name="AMAZON_2018_10K",
        company="Amazon",
        doc_type="10k",
        doc_period=2018,
        doc_link="https://example.com/amazon-2018.pdf",
        page=page,
        content=content,
        similarity=similarity,
    )


INCOME = passage(
    "| Net sales | $ 232,887 | $ 177,866 |\n| Cost of sales | 139,156 | 111,934 |", page=38
)
BALANCE = passage("| Accounts payable | 38,192 | 34,616 |\n| Total assets | 162,648 |", page=40)
PASSAGES = [INCOME, BALANCE]


def reply(
    answer: str = "",
    cited: list[int] | None = None,
    calculations: list[tuple[str, list[str]]] = (),
    status: str = "answered",
    round_to: int | None = None,
) -> str:
    """The JSON a model would return, built from short tuples."""
    return json.dumps(
        {
            "status": status,
            "answer": answer,
            "cited_excerpts": [1] if cited is None else cited,
            "calculations": [{"operation": op, "inputs": inputs} for op, inputs in calculations],
            "round_to": round_to,
        }
    )
