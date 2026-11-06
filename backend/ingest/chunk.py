"""Split a Docling document into chunks of about `max_words` words.

A chunk never spans two pages, tables stay whole, and page headers and footers are left out.
"""

import re
from dataclasses import dataclass

from docling_core.types.doc import DocItemLabel, DoclingDocument, TableItem, TextItem

HEADING_LABELS = {DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE}


@dataclass
class Chunk:
    page: int  # 1-based PDF page
    chunk_index: int  # order within the page
    content: str
    is_table: bool = False


def compact_table(markdown: str) -> str:
    """Drop the column padding Docling adds to markdown tables."""
    markdown = re.sub(r"-{3,}", "---", markdown)
    return re.sub(r" {2,}", " ", markdown).strip()


def chunk_document(doc: DoclingDocument, max_words: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    next_index: dict[int, int] = {}
    buffer: list[str] = []
    buffer_words = 0
    buffer_page = 0
    heading = ""  # latest heading, used to title tables

    def add_chunk(page: int, content: str, is_table: bool = False) -> None:
        index = next_index.get(page, 0)
        next_index[page] = index + 1
        chunks.append(Chunk(page, index, content, is_table))

    def close_chunk() -> None:
        nonlocal buffer, buffer_words
        if buffer:
            add_chunk(buffer_page, "\n".join(buffer))
        buffer, buffer_words = [], 0

    for item, _ in doc.iterate_items():
        if not item.prov:
            continue

        if isinstance(item, TableItem):
            # Skip the table of contents: it matches many questions and answers none.
            if item.label == DocItemLabel.DOCUMENT_INDEX:
                continue
            table = compact_table(item.export_to_markdown(doc=doc))
            if table:
                close_chunk()
                title = item.caption_text(doc) or heading
                page = item.prov[0].page_no  # cited to the page the table starts on
                add_chunk(page, f"{title}\n{table}" if title else table, is_table=True)
            continue

        if not isinstance(item, TextItem) or not item.text.strip():
            continue
        if item.label in HEADING_LABELS:
            heading = " ".join(item.text.split())

        for page, text in page_parts(item):
            words = text.split()
            if not words:
                continue
            if page != buffer_page:
                close_chunk()
                buffer_page = page

            # Split paragraphs longer than a chunk.
            for start in range(0, len(words), max_words):
                piece = words[start : start + max_words]
                if buffer_words + len(piece) > max_words:
                    close_chunk()
                buffer.append(" ".join(piece))
                buffer_words += len(piece)

    close_chunk()
    return chunks


def page_parts(item: TextItem) -> list[tuple[int, str]]:
    """Split text that runs across pages into (page, text) parts."""
    if len({p.page_no for p in item.prov}) == 1:
        return [(item.prov[0].page_no, item.text)]
    return [(p.page_no, item.text[p.charspan[0] : p.charspan[1]]) for p in item.prov]
