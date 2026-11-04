"""The answer-writing model: reply schema, prompt and Groq call.

The model only writes and cites. It never does arithmetic or decides whether
an answer is correct; Python checks its reply (see answer.py).
"""

import os
from typing import Literal, Protocol

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from figures import Operation
from retrieval import Passage


class UsedNumber(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str  # exactly as written in the excerpt, e.g. "$1,577" or "(1,577)"
    excerpt: int  # the excerpt it was copied from (0 for an earlier result like "{c1}")


class Calculation(BaseModel):
    """A calculation the model asks for; Python does the arithmetic."""

    model_config = ConfigDict(extra="forbid")

    operation: Operation
    inputs: list[UsedNumber]  # percent_change: [old, new]; ratio: [top, bottom]; difference: a - b


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "not_in_excerpts"]
    answer: str  # may contain {c1}, {c2}... where calculation results go
    cited_excerpts: list[int]
    numbers: list[UsedNumber]
    calculations: list[Calculation]


class Model(Protocol):
    """Anything that turns a prompt into raw reply text; tests pass a fake."""

    def __call__(self, prompt: str) -> str: ...


INSTRUCTIONS = """You answer questions about SEC filings using ONLY the numbered excerpts below.

Rules:
- Use only facts stated in the excerpts. Never use outside knowledge.
- If the excerpts do not contain what is needed, set status to "not_in_excerpts" \
and leave answer empty and all lists empty.
- Copy every number exactly as written in an excerpt. Never round, convert units \
or rewrite a number (do not turn "1,577" million into "1.6 billion"). If the question \
asks for one unit but the excerpt uses another, give the figure as written with the \
excerpt's unit (e.g. "$381,603 thousand"); never divide by 1,000 to convert it.
- Write years in full (2022, not FY22).
- Never do arithmetic yourself. If the answer needs a calculation, add it to \
calculations with one of these operations and its inputs copied from the excerpts:
  percent_change: inputs [old, new]
  ratio: inputs [numerator, denominator]
  difference: inputs [a, b] meaning a minus b
  sum: two or more inputs
  Then write {c1} in the answer where the first calculation's result goes, {c2} \
for the second, and so on. For a two-step calculation, an input may be {c1} \
(with excerpt 0) to use an earlier result, e.g. gross margin = ratio of {c1} to revenue.
- Put the number of every excerpt you relied on in cited_excerpts.
- List every number that appears in your answer in numbers, with the excerpt it came \
from. Years and fiscal periods count. Do not list the {c1} placeholders.
- Keep the answer short: one to three sentences, with units (e.g. "$ millions")."""


def build_prompt(question: str, passages: list[Passage]) -> str:
    excerpts = "\n\n".join(
        f"[Excerpt {i}] {p.company} {p.doc_type.upper()} {p.doc_period}, page {p.page}\n{p.content}"
        for i, p in enumerate(passages, 1)
    )
    return f"{INSTRUCTIONS}\n\nExcerpts:\n\n{excerpts}\n\nQuestion: {question}"


class GroqModel:
    """Calls Groq with a strict reply schema. last_tokens records each call's usage for the eval."""

    def __init__(self) -> None:
        self.client = OpenAI(
            base_url=os.environ["GROQ_BASE_URL"], api_key=os.environ["GROQ_API_KEY"]
        )
        self.schema = {
            "type": "json_schema",
            "json_schema": {"name": "reply", "strict": True, "schema": Reply.model_json_schema()},
        }
        self.last_tokens = 0

    def __call__(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=os.environ["GROQ_MODEL"],
            # Groq recommends putting all instructions in the user message for reasoning models.
            messages=[{"role": "user", "content": prompt}],
            response_format=self.schema,
            reasoning_effort=os.environ["GROQ_REASONING_EFFORT"],
            max_completion_tokens=int(os.environ["GROQ_MAX_COMPLETION_TOKENS"]),
            temperature=0,
            extra_body={"include_reasoning": False},
        )
        self.last_tokens = response.usage.total_tokens if response.usage else 0
        return response.choices[0].message.content or ""
