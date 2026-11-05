"""Run FilingCite on the eval questions, saving one result per question as it goes.

Usage (from backend/):
    uv run --env-file ../.env python -m evals.run --set subset40 --name subset40
    uv run --env-file ../.env python -m evals.run --set full --name full

Re-running with the same --name resumes, e.g. after the API's daily limit stops a run.
The model is called even below MIN_SIMILARITY so evals.score can try other thresholds,
and each reply is checked with the number check on and off.
"""

import argparse
import json
import os
from pathlib import Path

from answer import respond
from db import connect
from llm import build_prompt, chat_model
from retrieval import search

HERE = Path(__file__).parent


def read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text().splitlines() if path.exists() else []
    return [json.loads(line) for line in lines if line.strip()]


def load_questions(which: str) -> list[dict]:
    """FinanceBench questions (all, or the fixed 40) plus the should-refuse questions."""
    financebench = Path(os.environ["FINANCEBENCH_DIR"]) / "data/financebench_open_source.jsonl"
    subset = set((HERE / "subset40.txt").read_text().split()) if which == "subset40" else None
    questions = [
        {
            "id": q["financebench_id"],
            "question": q["question"],
            "expected": q["answer"],
            # FinanceBench pages are 0-based; ours are 1-based.
            "evidence": [[e["doc_name"], e["evidence_page_num"] + 1] for e in q["evidence"]],
        }
        for q in read_jsonl(financebench)
        if subset is None or q["financebench_id"] in subset
    ]
    refusals = read_jsonl(HERE / "refusal_questions.jsonl")
    return questions + [{**q, "expected": None, "evidence": []} for q in refusals]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["subset40", "full"], required=True)
    parser.add_argument("--name", required=True, help="results go to evals/results/<name>.jsonl")
    parser.add_argument("--limit", type=int, help="stop after this many new questions")
    args = parser.parse_args()

    path = HERE / "results" / f"{args.name}.jsonl"
    done = {r["id"] for r in read_jsonl(path)}
    todo = [q for q in load_questions(args.set) if q["id"] not in done][: args.limit]
    print(f"{len(done)} done, {len(todo)} to go -> {path}", flush=True)

    model = chat_model()
    path.parent.mkdir(exist_ok=True)
    with path.open("a") as out:
        for i, q in enumerate(todo, 1):
            with connect() as conn:  # a fresh connection each time: Neon suspends idle computes
                passages = search(conn, q["question"], int(os.environ["RETRIEVAL_TOP_K"]))
            raw = model(build_prompt(q["question"], passages))
            result = {
                **q,
                "retrieved": [[p.doc_name, p.page] for p in passages],
                "top_similarity": max(p.similarity for p in passages),
                "on": respond(raw, passages, q["question"]).model_dump(),
                "off": respond(raw, passages, q["question"], verify_numbers=False).model_dump(),
            }
            out.write(json.dumps(result) + "\n")
            out.flush()
            print(
                f"[{i}/{len(todo)}] {q['id']}: {result['on']['refusal'] or 'answered'}", flush=True
            )


if __name__ == "__main__":
    main()
