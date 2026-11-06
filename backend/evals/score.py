"""Grade saved eval results and print the scorecard. Python grades; no AI judges answers.

Usage (from backend/):  uv run --env-file ../.env python -m evals.score --name full

- Found the right page: a FinanceBench evidence page is among the retrieved chunks.
- Answered correctly: for FinanceBench answers that are a short number ("$1577.00", "65.4%"),
  the answer contains a number within 1% of it, ignoring sign, ratio vs percentage and
  thousands vs millions. Written answers need judgement, so they aren't marked right or
  wrong.
- Refused correctly: a should-refuse question was not answered.
- Blocked a number: the number check refused an answer the model had written.
"""

import argparse
import os
from decimal import Decimal

from evals.run import HERE, read_jsonl
from figures import NUMBER


def numbers(text: str) -> list[Decimal]:
    return [Decimal(n.replace(",", "")) for n in NUMBER.findall(text)]


def grade(r: dict, mode: str, threshold: Decimal) -> dict:
    """What the user would see at this threshold, with the number check on or off, graded."""
    weak = Decimal(str(r["top_similarity"])) < threshold
    shown = {"answered": False, "refusal": "weak_match"} if weak else r[mode]
    expected = r["expected"]
    target = numbers(expected)[:1] if expected and len(expected.split()) <= 6 else []
    found = numbers(shown["answer"]) if shown["answered"] else []
    scales = (1, 100, Decimal("0.01"), 1000, Decimal("0.001"))
    return {
        "should_refuse": expected is None,
        "answered": shown["answered"],
        "blocked": shown["refusal"] == "unverified_number",
        "hit": any(e in r["retrieved"] for e in r["evidence"]),
        "numeric": bool(target),
        "correct": any(
            abs(v * s - abs(t)) <= max(abs(t) / 100, Decimal("0.005"))
            for t in target
            for v in found
            for s in scales
        ),
    }


def summarize(records: list[dict], mode: str, threshold: Decimal) -> dict:
    graded = [grade(r, mode, threshold) for r in records]
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
        "blocked": sum(g["blocked"] for g in graded),
    }


def pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100 * part / whole:.0f}%)" if whole else "n/a"


def scorecard(records: list[dict], threshold: Decimal, name: str) -> str:
    on, off = summarize(records, "on", threshold), summarize(records, "off", threshold)
    lines = [
        f"# FilingCite scorecard: {name}",
        "",
        (
            f"{on['questions']} FinanceBench + {on['should_refuse']} should-refuse questions, "
            f"MIN_SIMILARITY {threshold}, {os.environ['LLM_MODEL']}."
        ),
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Found the right page | {pct(on['hit'], on['questions'])} |",
        f"| Answered correctly (numeric, within 1%) | {pct(on['correct'], on['numeric'])} |",
        f"| Refused correctly | {pct(on['refused'], on['should_refuse'])} |",
        f"| Blocked a number | {on['blocked']} |",
        "",
        "## Number check off vs on",
        "",
        "| | Off | On |",
        "| --- | --- | --- |",
        f"| FinanceBench answered | {off['answered']} | {on['answered']} |",
        f"| Numeric answers correct | {off['correct']} | {on['correct']} |",
        f"| Numeric answers wrong | {off['wrong']} | {on['wrong']} |",
        "",
        "## Refusal threshold sweep",
        "",
        "| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |",
        "| --- | --- | --- | --- |",
    ]
    for t in (Decimal(t) / 100 for t in range(60, 81, 2)):
        s = summarize(records, "on", t)
        refused = f"{s['refused']}/{s['should_refuse']}"
        lines.append(f"| {t} | {s['answered']} | {s['correct']} | {refused} |")
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
