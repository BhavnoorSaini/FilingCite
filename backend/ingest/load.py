"""Parse, chunk, embed and load the FinanceBench filings into Neon. Runs on a Mac; never deployed.

Usage (from backend/):  uv run --group ingest --env-file ../.env python -m ingest.load

Skips filings already loaded, so an interrupted run picks up where it stopped. Docling's
output is cached as JSON, and each filing is saved in one transaction, so there are no
duplicates.
"""

import json
import os
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
    # A fresh connection per filing: Neon sleeps while a long PDF parses.
    with connect() as conn, conn.transaction():
        filing_id = conn.execute(
            "INSERT INTO filings (doc_name, company, doc_type, doc_period, doc_link)"
            " VALUES (%(doc_name)s, %(company)s, %(doc_type)s, %(doc_period)s, %(doc_link)s)"
            " RETURNING id",
            meta,
        ).fetchone()[0]
        conn.cursor().executemany(
            "INSERT INTO chunks (filing_id, page, chunk_index, is_table, content, embedding)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (filing_id, c.page, c.chunk_index, c.is_table, c.content, e)
                for c, e in zip(chunks, embeddings)
            ],
        )


def main() -> None:
    root = BACKEND_DIR / os.environ["FINANCEBENCH_DIR"]  # absolute paths stay as-is
    cache_dir = BACKEND_DIR / os.environ["PARSED_DIR"]
    metadata = {
        d["doc_name"]: d for d in read_jsonl(root / "data/financebench_document_information.jsonl")
    }
    questions = read_jsonl(root / "data/financebench_open_source.jsonl")
    names = sorted({q["doc_name"] for q in questions})
    with connect() as conn:
        loaded = {r[0] for r in conn.execute("SELECT doc_name FROM filings")}

    options = PdfPipelineOptions(do_ocr=False)  # FinanceBench PDFs have a text layer
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    for i, name in enumerate(names, 1):
        if name in loaded:
            continue
        doc = parse(root / "pdfs" / f"{name}.pdf", cache_dir, converter)
        chunks = chunk_document(doc, int(os.environ["CHUNK_WORDS"]))
        save(metadata[name], chunks, embed_passages([c.content for c in chunks]))
        print(f"[{i}/{len(names)}] {name}: {len(chunks)} chunks", flush=True)


if __name__ == "__main__":
    main()
