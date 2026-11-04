"""Run FilingCite on the eval questions and save one result per question.

Usage (from backend/):
    uv run --env-file ../.env python -m evals.run --set subset40 --name baseline
    uv run --env-file ../.env python -m evals.run --set full --name full-1

Re-running with the same --name resumes: finished questions are skipped. When Groq's
daily limit is hit, the run stops cleanly; run the same command again the next day.

The model is called even below MIN_SIMILARITY so the scorecard can try other thresholds
offline, and each reply is checked with the number check on and off.
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

import openai

from answer import respond
from db import connect
from llm import GroqModel, build_prompt
from retrieval import search

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"
RETRIES = 5


class DailyLimitReached(Exception):
    pass


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_questions(which: str) -> list[dict]:
    """FinanceBench questions (all or the fixed subset) plus the should-refuse questions."""
    financebench = read_jsonl(
        Path(os.environ["FINANCEBENCH_DIR"]) / "data" / "financebench_open_source.jsonl"
    )
    if which == "subset40":
        lines = (EVALS_DIR / "subset40.txt").read_text().splitlines()
        keep = {line for line in lines if line and not line.startswith("#")}
        financebench = [q for q in financebench if q["financebench_id"] in keep]

    questions = [
        {
            "id": q["financebench_id"],
            "set": "financebench",
            "question": q["question"],
            "question_type": q["question_type"],
            "expected": q["answer"],
            # FinanceBench pages are 0-based; ours are 1-based.
            "evidence": sorted(
                {(e["doc_name"], e["evidence_page_num"] + 1) for e in q["evidence"]}
            ),
        }
        for q in financebench
    ]
    questions += [
        {**q, "set": "refusal", "question_type": q["category"], "expected": None, "evidence": []}
        for q in read_jsonl(EVALS_DIR / "refusal_questions.jsonl")
    ]
    return questions


def wait_seconds(error: openai.RateLimitError) -> float:
    """How long Groq asks us to wait, from the retry-after header or the message."""
    header = error.response.headers.get("retry-after") if error.response else None
    if header:
        return float(header)
    match = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(error))
    if match:
        return int(match.group(1) or 0) * 60 + float(match.group(2))
    return 30.0


def call_model(model: GroqModel, prompt: str) -> str:
    for _ in range(RETRIES):
        try:
            return model(prompt)
        except openai.RateLimitError as error:
            if re.search(r"per day|\(TPD\)|\(RPD\)", str(error)):
                raise DailyLimitReached(str(error)) from error
            pause = wait_seconds(error) + 1
            print(f"  rate limited, waiting {pause:.0f}s")
            time.sleep(pause)
    raise RuntimeError(f"Still rate limited after {RETRIES} tries")


def run_one(model: GroqModel, item: dict) -> dict:
    with connect() as conn:  # fresh connection per question: Neon suspends idle computes
        passages = search(conn, item["question"], int(os.environ["RETRIEVAL_TOP_K"]))
    raw = call_model(model, build_prompt(item["question"], passages))
    return {
        **item,
        "retrieved": [[p.doc_name, p.page, p.is_table, round(p.similarity, 4)] for p in passages],
        "chunk_ids": [p.chunk_id for p in passages],  # lets evals.recheck rebuild the passages
        "top_similarity": round(passages[0].similarity, 4),
        "raw_reply": raw,
        "tokens": model.last_tokens,
        "on": respond(raw, passages, verify_numbers=True).model_dump(),
        "off": respond(raw, passages, verify_numbers=False).model_dump(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["subset40", "full"], required=True)
    parser.add_argument("--name", required=True, help="results go to evals/results/<name>.jsonl")
    parser.add_argument("--limit", type=int, help="stop after this many new questions")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{args.name}.jsonl"
    done = {r["id"] for r in read_jsonl(path)}
    todo = [q for q in load_questions(args.set) if q["id"] not in done][: args.limit]
    print(f"{len(done)} already done, {len(todo)} to go -> {path}")

    model = GroqModel()
    tokens = 0
    with path.open("a") as out:
        for i, item in enumerate(todo, 1):
            try:
                result = run_one(model, item)
            except DailyLimitReached as error:
                print(f"\nGroq's daily limit reached; progress is saved. Run again later.\n{error}")
                break
            out.write(json.dumps(result) + "\n")
            out.flush()
            tokens += result["tokens"]
            outcome = result["on"]["refusal"] or "answered"
            print(f"[{i}/{len(todo)}] {item['id']}: {outcome} ({result['tokens']} tokens)")
    print(f"Tokens used this run: {tokens}")


if __name__ == "__main__":
    main()
