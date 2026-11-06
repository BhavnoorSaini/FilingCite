"""Grade saved eval results and write the scorecard. Python grades; no AI judges.

Usage (from backend/):  uv run --env-file ../.env python -m evals.score --name full

- Found the right page: an evidence page is among the retrieved chunks.
- Answered correctly: for short numeric answers ("$1577.00", "65.4%"), the answer has a
  number within 1% of it, ignoring sign and scale (ratio vs percent, thousands vs millions).
  Written answers need a person to judge, so they aren't graded.
- Refused correctly: a should-refuse question wasn't answered.
"""

import argparse
import os
from decimal import Decimal

from evals.run import HERE, read_jsonl
from figures import NUMBER


def numbers(text: str) -> list[Decimal]:
    return [Decimal(n.replace(",", "")) for n in NUMBER.findall(text)]


def grade(r: dict, threshold: Decimal) -> dict:
    """What the user would see at this threshold, graded."""
    weak = Decimal(str(r["top_similarity"])) < threshold
    shown = {"answered": False} if weak else r["response"]
    expected = r["expected"]
    target = numbers(expected)[:1] if expected and len(expected.split()) <= 6 else []
    found = numbers(shown["answer"]) if shown["answered"] else []
    scales = (1, 100, Decimal("0.01"), 1000, Decimal("0.001"))
    return {
        "should_refuse": expected is None,
        "answered": shown["answered"],
        "hit": any(e in r["retrieved"] for e in r["evidence"]),
        "numeric": bool(target),
        "correct": any(
            abs(v * s - abs(t)) <= max(abs(t) / 100, Decimal("0.005"))
            for t in target
            for v in found
            for s in scales
        ),
    }


def summarize(records: list[dict], threshold: Decimal) -> dict:
    graded = [grade(r, threshold) for r in records]
    financebench = [g for g in graded if not g["should_refuse"]]
    numeric = [g for g in financebench if g["numeric"]]
    should_refuse = [g for g in graded if g["should_refuse"]]
    return {
        "questions": len(financebench),
        "hit": sum(g["hit"] for g in financebench),
        "answered": sum(g["answered"] for g in financebench),
        "numeric": len(numeric),
        "correct": sum(g["correct"] for g in numeric),
        "wrong": sum(g["answered"] and not g["correct"] for g in numeric),
        "should_refuse": len(should_refuse),
        "refused": sum(not g["answered"] for g in should_refuse),
    }


def pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100 * part / whole:.0f}%)" if whole else "n/a"


def scorecard(records: list[dict], threshold: Decimal, name: str) -> str:
    s = summarize(records, threshold)
    lines = [
        f"# FilingCite scorecard: {name}",
        "",
        (
            f"{s['questions']} FinanceBench + {s['should_refuse']} should-refuse questions, "
            f"MIN_SIMILARITY {threshold}, {os.environ['LLM_MODEL']}."
        ),
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Found the right page | {pct(s['hit'], s['questions'])} |",
        f"| FinanceBench questions answered | {s['answered']}/{s['questions']} |",
        f"| Answered correctly (numeric, within 1%) | {pct(s['correct'], s['numeric'])} |",
        f"| Numeric answers wrong | {s['wrong']} |",
        f"| Refused correctly | {pct(s['refused'], s['should_refuse'])} |",
        "",
        "## Refusal threshold sweep",
        "",
        "| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |",
        "| --- | --- | --- | --- |",
    ]
    for t in (Decimal(t) / 100 for t in range(60, 81, 2)):
        at = summarize(records, t)
        refused = f"{at['refused']}/{at['should_refuse']}"
        lines.append(f"| {t} | {at['answered']} | {at['correct']} | {refused} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    records = read_jsonl(HERE / "results" / f"{args.name}.jsonl")
    text = scorecard(records, Decimal(os.environ["MIN_SIMILARITY"]), args.name)
    (HERE / "results" / f"{args.name}.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
