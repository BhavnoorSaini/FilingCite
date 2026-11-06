"""The model's reply format, its prompt and the API call.

The model only writes and cites; Python checks everything it says (answer.py).
"""

import json
import os
from collections.abc import Callable
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from figures import Operation
from retrieval import Passage

Model = Callable[[str], str]  # prompt in, raw reply out; tests pass a fake


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")  # required for strict structured outputs


class UsedNumber(Strict):
    value: str  # as written in the excerpt, e.g. "(1,577)"
    excerpt: int  # the excerpt it's from; 0 is the question


class Calculation(Strict):
    operation: Operation
    inputs: list[UsedNumber]


class Reply(Strict):
    status: Literal["answered", "not_in_excerpts"]
    answer: str  # may contain {c1}, {c2}... where calculation results go
    cited_excerpts: list[int]
    numbers: list[UsedNumber]
    calculations: list[Calculation]
    round_to: int | None  # decimal places the question asks for


INSTRUCTIONS = """You answer questions about SEC filings using ONLY the numbered excerpts below.

Rules:
- Use only facts stated in the excerpts. Never use outside knowledge.
- If the excerpts do not contain what is needed, set status to "not_in_excerpts" \
and leave answer empty and all lists empty.
- Copy every number exactly as written in an excerpt. Never round or rewrite a number \
(do not turn "2,345" million into "2.3 billion").
- Write years in full (2022, not FY22).
- Never do arithmetic yourself. If the answer needs a calculation, add it to calculations \
with one of these operations and its inputs copied from the excerpts:
  percent_change: inputs [old, new]
  cagr: inputs [start, end, years], giving compound annual growth as a percent; years \
may be a difference of two years
  percentage: inputs [part, whole], giving part / whole as a percent; use it for any \
margin or "as a %" figure
  ratio: inputs [numerator, denominator], for plain ratios such as a current ratio
  difference: inputs [a, b] meaning a minus b
  sum: two or more inputs
  average: two or more inputs (e.g. average total assets over two years); never divide \
a sum by 2 instead
  product: two or more inputs multiplied (e.g. 365 times a ratio)
- Calculation inputs may also be, with excerpt 0: an earlier result such as {c1}; a \
number the question itself gives (e.g. 365 in a formula it defines); or 1,000 or \
1,000,000 to convert units.
- All inputs to one calculation must be in the same unit (e.g. all in $ millions). If \
two tables use different units, convert one first. If the question asks for a different \
unit than the excerpt's, give the figure with the excerpt's unit (e.g. "$45,210 \
thousand") or convert it with a calculation.
- Set round_to to the decimal places the question asks for (1 for "round to one decimal \
place"), or null if it doesn't ask. Python does the rounding.
- Write {c1} in the answer where the first calculation's result goes, {c2} for the \
second, and so on. Every result must be used, in the answer or in a later calculation. \
Percentages come with "%"; write any other unit yourself (e.g. "${c1} million").
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


def chat_model() -> Model:
    """Call an OpenAI-compatible API (Groq or OpenRouter) with a strict reply schema."""
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
    schema = {"name": "reply", "strict": True, "schema": Reply.model_json_schema()}

    def call(prompt: str) -> str:
        response = client.chat.completions.create(
            model=os.environ["LLM_MODEL"],
            # Reasoning models do best with everything in the user message.
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": schema},
            max_completion_tokens=int(os.environ["LLM_MAX_COMPLETION_TOKENS"]),
            temperature=0,
            extra_body=json.loads(os.environ["LLM_EXTRA_BODY"]),
        )
        return response.choices[0].message.content or ""

    return call
