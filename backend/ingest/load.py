"""Parse, chunk, embed and load FinanceBench filings into Neon. Mac only; never deployed.

Usage (from backend/):
    uv run --group ingest --env-file ../.env python -m ingest.load              # every filing used by a question
    uv run --group ingest --env-file ../.env python -m ingest.load 3M_2018_10K  # specific filings
    add --force to reload filings that are already loaded

Docling's output is cached as JSON, so re-runs skip the slow parse. Re-running is safe: a
filing's chunks are replaced in one transaction, never duplicated.
"""

import argparse
import json
import os
import time
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DoclingDocument

from db import connect
from embedding import BACKEND_DIR, embed_passages
from ingest.chunk import chunk_document


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def parse(pdf: Path, cache_dir: Path, converter: DocumentConverter) -> DoclingDocument:
    cached = cache_dir / f"{pdf.stem}.json"
    if not cached.exists():
        result = converter.convert(pdf)
        cache_dir.mkdir(parents=True, exist_ok=True)
        result.document.save_as_json(cached)
        return result.document
    return DoclingDocument.load_from_json(cached)


def save(meta: dict, chunks, embeddings) -> None:
    # A fresh connection per filing: Neon suspends idle computes while a long PDF parses.
    with connect() as conn, conn.transaction():
        filing_id = conn.execute(
            """
            INSERT INTO filings (doc_name, company, doc_type, doc_period, doc_link)
            VALUES (%(doc_name)s, %(company)s, %(doc_type)s, %(doc_period)s, %(doc_link)s)
            ON CONFLICT (doc_name) DO UPDATE SET company = EXCLUDED.company,
                doc_type = EXCLUDED.doc_type, doc_period = EXCLUDED.doc_period,
                doc_link = EXCLUDED.doc_link
            RETURNING id
            """,
            {k: meta.get(k) for k in ("doc_name", "company", "doc_type", "doc_period", "doc_link")},
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

    root = BACKEND_DIR / os.environ["FINANCEBENCH_DIR"]  # absolute paths stay as-is
    cache_dir = BACKEND_DIR / os.environ["PARSED_DIR"]
    info = read_jsonl(root / "data/financebench_document_information.jsonl")
    metadata = {d["doc_name"]: d for d in info}
    questions = read_jsonl(root / "data/financebench_open_source.jsonl")
    names = args.doc_names or sorted({q["doc_name"] for q in questions})
    with connect() as conn:
        loaded = {r[0] for r in conn.execute("SELECT doc_name FROM filings")}

    options = PdfPipelineOptions(do_ocr=False)  # FinanceBench PDFs have a text layer
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    for i, name in enumerate(names, 1):
        if name in loaded and not args.force:
            continue
        start = time.monotonic()
        doc = parse(root / "pdfs" / f"{name}.pdf", cache_dir, converter)
        chunks = chunk_document(doc, int(os.environ["CHUNK_WORDS"]))
        save(metadata[name], chunks, embed_passages([c.content for c in chunks]))
        print(f"[{i}/{len(names)}] {name}: {len(chunks)} chunks in {time.monotonic() - start:.0f}s")


if __name__ == "__main__":
    main()
