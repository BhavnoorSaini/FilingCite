"""Parse, chunk, embed and load FinanceBench filings into Neon. Mac only; never deployed.

Usage (from backend/):
    uv run --group ingest --env-file ../.env python -m ingest.load              # every filing used by a question
    uv run --group ingest --env-file ../.env python -m ingest.load 3M_2018_10K  # specific filings
    add --force to reload filings that are already loaded

Re-running is safe: a filing's chunks are replaced in one transaction, never duplicated.
"""

import argparse
import json
import logging
import os
import time
from pathlib import Path

from db import connect
from embedding import BACKEND_DIR, embed_passages
from ingest.chunk import chunk_document
from ingest.parse import make_converter, parse

log = logging.getLogger("ingest")

FILING_FIELDS = ("doc_name", "company", "doc_type", "doc_period", "doc_link")


def env_path(var: str) -> Path:
    return BACKEND_DIR / os.environ[var]  # relative to backend/; absolute paths stay as-is


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def save_filing(meta: dict, chunks, embeddings) -> None:
    # A fresh connection per filing: Neon suspends idle computes while a long PDF parses.
    with connect() as conn, conn.transaction():
        filing_id = conn.execute(
            """
            INSERT INTO filings (doc_name, company, doc_type, doc_period, doc_link)
            VALUES (%(doc_name)s, %(company)s, %(doc_type)s, %(doc_period)s, %(doc_link)s)
            ON CONFLICT (doc_name) DO UPDATE SET
                company = EXCLUDED.company, doc_type = EXCLUDED.doc_type,
                doc_period = EXCLUDED.doc_period, doc_link = EXCLUDED.doc_link
            RETURNING id
            """,
            meta,
        ).fetchone()[0]
        conn.execute("DELETE FROM chunks WHERE filing_id = %s", (filing_id,))
        conn.cursor().executemany(
            "INSERT INTO chunks (filing_id, page, chunk_index, is_table, content, embedding)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (filing_id, c.page, c.chunk_index, c.is_table, c.content, e)
                for c, e in zip(chunks, embeddings)
            ],
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("doc_names", nargs="*", help="default: every filing used by a question")
    parser.add_argument("--force", action="store_true", help="reload filings already loaded")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    data_dir = env_path("FINANCEBENCH_DIR") / "data"
    pdf_dir = env_path("FINANCEBENCH_DIR") / "pdfs"
    parsed_dir = env_path("PARSED_DIR")
    max_words = int(os.environ["CHUNK_WORDS"])

    metadata = {
        d["doc_name"]: d for d in read_jsonl(data_dir / "financebench_document_information.jsonl")
    }
    names = args.doc_names or sorted(
        {q["doc_name"] for q in read_jsonl(data_dir / "financebench_open_source.jsonl")}
    )
    with connect() as conn:
        loaded = {
            row[0]
            for row in conn.execute(
                "SELECT doc_name FROM filings f"
                " WHERE EXISTS (SELECT 1 FROM chunks c WHERE c.filing_id = f.id)"
            )
        }

    converter = make_converter()
    for i, name in enumerate(names, 1):
        progress = f"[{i}/{len(names)}] {name}"
        if name in loaded and not args.force:
            log.info("%s: already loaded, skipping", progress)
            continue
        start = time.monotonic()
        doc = parse(pdf_dir / f"{name}.pdf", parsed_dir, converter)
        chunks = chunk_document(doc, max_words)
        embeddings = embed_passages([c.content for c in chunks])
        save_filing({k: metadata[name].get(k) for k in FILING_FIELDS}, chunks, embeddings)
        log.info("%s: %d chunks in %.0fs", progress, len(chunks), time.monotonic() - start)


if __name__ == "__main__":
    main()
