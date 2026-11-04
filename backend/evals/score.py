"""Grade saved eval results and print the scorecard. Python grades; no AI judges answers.

Usage (from backend/):
    uv run --env-file ../.env python -m evals.score --name baseline
    uv run --env-file ../.env python -m evals.score --name baseline --threshold 0.65

Grading rules:
- Found the right page: a FinanceBench evidence page is among the retrieved chunks.
- Answered correctly: only for FinanceBench answers that are a short number (e.g. "$1577.00",
  "65.4%"). Correct if the answer contains a number within 1% of it, ignoring sign,
  ratio vs percentage (0.40 vs 39.7%) and thousands vs millions ("$302,578 thousand" vs
  "$303" million), since filings use both units. Longer, written answers
  are not auto-graded, since that would need judgement; for them we report whether the
  answer cited the evidence page.
- Refused correctly: a should-refuse question was not answered.
- Blocked a number: the number check refused an answer the model had written.
"""

import argparse
import os
from decimal import Decimal
from pathlib import Path

from evals.run import RESULTS_DIR, read_jsonl
from figures import NUMBER

SWEEP = [Decimal(t) / 100 for t in range(60, 81)]


def first_number(text: str) -> Decimal | None:
    match = NUMBER.search(text)
    return Decimal(match.group().replace(",", "")) if match else None


def numeric_expected(record: dict) -> Decimal | None:
    """The expected number, if the FinanceBench answer is a short number."""
    expected = record["expected"]
    if record["set"] != "financebench" or len(expected.split()) > 6:
        return None
    return first_number(expected)


def matches(answer: str, expected: Decimal) -> bool:
    def close(value: Decimal) -> bool:
        return abs(value - abs(expected)) <= max(abs(expected) / 100, Decimal("0.005"))

    values = [Decimal(m.replace(",", "")) for m in NUMBER.findall(answer)]
    # Ratio vs percentage (x100) and thousands vs millions (x1000) are the same figure.
    scales = (1, 100, Decimal("0.01"), 1000, Decimal("0.001"))
    return any(close(v * s) for v in values for s in scales)


def outcome(record: dict, mode: str, threshold: Decimal) -> dict:
    """What the user would see at this threshold, with the number check on or off."""
    if Decimal(str(record["top_similarity"])) < threshold:
        return {"answered": False, "refusal": "weak_match", "answer": None, "citations": []}
    return record[mode]


def grade(record: dict, mode: str, threshold: Decimal) -> dict:
    shown = outcome(record, mode, threshold)
    evidence = {tuple(e) for e in record["evidence"]}
    cited = {(c["doc_name"], c["page"]) for c in shown["citations"]}
    expected = numeric_expected(record)
    return {
        "answered": shown["answered"],
        "refusal": shown["refusal"],
        "retrieval_hit": bool(evidence & {(r[0], r[1]) for r in record["retrieved"]}),
        "cited_evidence": shown["answered"] and bool(evidence & cited),
        "gradable": expected is not None,
        "correct": expected is not None
        and shown["answered"]
        and matches(shown["answer"], expected),
    }


def pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({100 * part / whole:.0f}%)" if whole else "n/a"


def summarize(records: list[dict], mode: str, threshold: Decimal) -> dict:
    fb = [grade(r, mode, threshold) for r in records if r["set"] == "financebench"]
    refuse = [grade(r, mode, threshold) for r in records if r["set"] == "refusal"]
    gradable = [g for g in fb if g["gradable"]]
    written = [g for g in fb if not g["gradable"]]
    return {
        "fb": len(fb),
        "retrieval_hit": sum(g["retrieval_hit"] for g in fb),
        "answered": sum(g["answered"] for g in fb),
        "gradable": len(gradable),
        "gradable_answered": sum(g["answered"] for g in gradable),
        "correct": sum(g["correct"] for g in gradable),
        "written": len(written),
        "written_answered": sum(g["answered"] for g in written),
        "written_cited": sum(g["cited_evidence"] for g in written),
        "refuse": len(refuse),
        "refused": sum(not g["answered"] for g in refuse),
        "blocked": sum(g["refusal"] == "unverified_number" for g in fb + refuse),
        "reasons": {
            reason: sum(g["refusal"] == reason for g in fb)
            for reason in sorted({g["refusal"] for g in fb if g["refusal"]})
        },
    }


def scorecard(records: list[dict], threshold: Decimal, name: str) -> str:
    on = summarize(records, "on", threshold)
    off = summarize(records, "off", threshold)
    tokens = sum(r["tokens"] for r in records)

    # What the number check blocked: would those answers have been right or wrong?
    blocked = [
        r
        for r in records
        if outcome(r, "on", threshold)["refusal"] == "unverified_number"
        and outcome(r, "off", threshold)["answered"]
    ]
    blocked_graded = [r for r in blocked if numeric_expected(r) is not None]
    blocked_wrong = sum(not grade(r, "off", threshold)["correct"] for r in blocked_graded)

    lines = [
        f"# FilingCite scorecard: {name}",
        "",
        (
            f"{on['fb']} FinanceBench questions + {on['refuse']} should-refuse questions, "
            f"MIN_SIMILARITY {threshold}, top {os.environ['RETRIEVAL_TOP_K']} chunks, "
            f"{os.environ['GROQ_MODEL']}. Tokens used: {tokens:,}."
        ),
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| Found the right page (evidence in retrieved chunks) | {pct(on['retrieval_hit'], on['fb'])} |",
        f"| Answered correctly (numeric answers within 1%) | {pct(on['correct'], on['gradable'])} |",
        f"| Refused correctly (should-refuse questions) | {pct(on['refused'], on['refuse'])} |",
        f"| Blocked a number (number check refusals) | {on['blocked']} |",
        "",
        "## Detail",
        "",
        (
            f"- Numeric questions answered: {pct(on['gradable_answered'], on['gradable'])}; "
            f"correct when answered: {pct(on['correct'], on['gradable_answered'])}"
        ),
        (
            f"- Written-answer questions answered: {pct(on['written_answered'], on['written'])}; "
            f"answer cited the evidence page: {pct(on['written_cited'], on['written'])}"
        ),
        f"- FinanceBench refusals by reason: {on['reasons']}",
        "",
        "## Number check off vs on",
        "",
        "| | Off | On |",
        "| --- | --- | --- |",
        f"| FinanceBench answered | {off['answered']} | {on['answered']} |",
        f"| Numeric answers correct | {off['correct']} | {on['correct']} |",
        (
            f"| Numeric answers wrong | {off['gradable_answered'] - off['correct']} "
            f"| {on['gradable_answered'] - on['correct']} |"
        ),
        (
            f"| Should-refuse questions answered | {off['refuse'] - off['refused']} "
            f"| {on['refuse'] - on['refused']} |"
        ),
        "",
        (
            f"Of {len(blocked)} blocked answers, {len(blocked_graded)} had a numeric expected answer; "
            f"{blocked_wrong} of those would have been wrong."
        ),
        "",
        "## Refusal threshold sweep (number check on)",
        "",
        "| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |",
        "| --- | --- | --- | --- |",
    ]
    for t in SWEEP:
        s = summarize(records, "on", t)
        lines.append(
            f"| {t} | {s['answered']}/{s['fb']} | {s['correct']}/{s['gradable']} "
            f"| {s['refused']}/{s['refuse']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--threshold", type=Decimal, help="default: MIN_SIMILARITY")
    args = parser.parse_args()

    records = read_jsonl(RESULTS_DIR / f"{args.name}.jsonl")
    if not records:
        raise SystemExit(f"No results for {args.name}")
    threshold = args.threshold or Decimal(os.environ["MIN_SIMILARITY"])
    text = scorecard(records, threshold, args.name)
    Path(RESULTS_DIR / f"{args.name}.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
