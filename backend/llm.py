"""The answer-writing model: reply schema, prompt and Groq call.

The model only writes and cites. It never does arithmetic or decides whether
an answer is correct; Python checks its reply (see answer.py).
"""

import os
from typing import Literal, Protocol

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from retrieval import Passage


class UsedNumber(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str  # exactly as written in the excerpt, e.g. "$1,577" or "(1,577)"
    excerpt: int  # the excerpt it was copied from


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "not_in_excerpts"]
    answer: str
    cited_excerpts: list[int]
    numbers: list[UsedNumber]


class Model(Protocol):
    """Anything that turns a prompt into raw reply text; tests pass a fake."""

    def __call__(self, prompt: str) -> str: ...


INSTRUCTIONS = """You answer questions about SEC filings using ONLY the numbered excerpts below.

Rules:
- Use only facts stated in the excerpts. Never use outside knowledge.
- If the excerpts do not contain what is needed, set status to "not_in_excerpts" \
and leave answer empty and both lists empty.
- Do not do any arithmetic. Report figures exactly as they appear; if the question \
needs a calculation, say which figures it would use instead of calculating.
- Put the number of every excerpt you relied on in cited_excerpts.
- List every number that appears in your answer in numbers, copied exactly as \
written in the excerpt, with the excerpt it came from. Years and fiscal periods count.
- Keep the answer short: one to three sentences, with units (e.g. "$ millions")."""


def build_prompt(question: str, passages: list[Passage]) -> str:
    excerpts = "\n\n".join(
        f"[Excerpt {i}] {p.company} {p.doc_type.upper()} {p.doc_period}, page {p.page}\n{p.content}"
        for i, p in enumerate(passages, 1)
    )
    return f"{INSTRUCTIONS}\n\nExcerpts:\n\n{excerpts}\n\nQuestion: {question}"


def groq_model() -> Model:
    client = OpenAI(base_url=os.environ["GROQ_BASE_URL"], api_key=os.environ["GROQ_API_KEY"])
    schema = {
        "type": "json_schema",
        "json_schema": {"name": "reply", "strict": True, "schema": Reply.model_json_schema()},
    }

    def call(prompt: str) -> str:
        response = client.chat.completions.create(
            model=os.environ["GROQ_MODEL"],
            # Groq recommends putting all instructions in the user message for reasoning models.
            messages=[{"role": "user", "content": prompt}],
            response_format=schema,
            reasoning_effort=os.environ["GROQ_REASONING_EFFORT"],
            max_completion_tokens=int(os.environ["GROQ_MAX_COMPLETION_TOKENS"]),
            temperature=0,
            extra_body={"include_reasoning": False},
        )
        return response.choices[0].message.content or ""

    return call
