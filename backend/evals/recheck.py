"""Re-apply the current checks to saved model replies, without calling Groq again.

Use after changing the number check or citation rules, then re-run evals.score.

Usage (from backend/):  uv run --env-file ../.env python -m evals.recheck --name baseline
"""

import argparse
import json
import os

from answer import respond
from db import connect
from evals.run import RESULTS_DIR, read_jsonl
from retrieval import Passage, search


def saved_passages(conn, record: dict) -> list[Passage]:
    """The passages the model saw, rebuilt from saved chunk ids (or by re-running the search)."""
    if "chunk_ids" not in record:  # older results: search again and confirm nothing changed
        passages = search(conn, record["question"], int(os.environ["RETRIEVAL_TOP_K"]))
        if [[p.doc_name, p.page] for p in passages] != [r[:2] for r in record["retrieved"]]:
            raise SystemExit(f"{record['id']}: retrieval changed since this run; can't recheck")
        return passages

    rows = conn.execute(
        """
        SELECT c.id, f.doc_name, f.company, f.doc_type, f.doc_period, f.doc_link,
               c.page, c.is_table, c.content
        FROM chunks c JOIN filings f ON f.id = c.filing_id
        WHERE c.id = ANY(%s)
        """,
        (record["chunk_ids"],),
    ).fetchall()
    by_id = {row[0]: row for row in rows}
    return [
        Passage(*by_id[chunk_id], similarity=retrieved[3])
        for chunk_id, retrieved in zip(record["chunk_ids"], record["retrieved"])
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    path = RESULTS_DIR / f"{args.name}.jsonl"
    records = read_jsonl(path)
    changed = 0
    with connect() as conn:
        for record in records:
            passages = saved_passages(conn, record)
            record["chunk_ids"] = [p.chunk_id for p in passages]
            for mode, verify in (("on", True), ("off", False)):
                new = respond(record["raw_reply"], passages, verify_numbers=verify).model_dump()
                changed += new != record[mode]
                record[mode] = new
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    print(f"Rechecked {len(records)} results; {changed} outcomes changed.")


if __name__ == "__main__":
    main()
