"""Chunking rules, on small hand-built Docling documents."""

from docling_core.types.doc import (
    BoundingBox,
    ContentLayer,
    DocItemLabel,
    DoclingDocument,
    ProvenanceItem,
    TableCell,
    TableData,
)

from ingest.chunk import chunk_document


def prov(page: int, start: int, end: int) -> ProvenanceItem:
    return ProvenanceItem(page_no=page, bbox=BoundingBox(l=0, t=0, r=1, b=1), charspan=(start, end))


def text(doc: DoclingDocument, body: str, page: int, label=DocItemLabel.TEXT, **kwargs) -> None:
    doc.add_text(label=label, text=body, prov=prov(page, 0, len(body)), **kwargs)


def table(doc: DoclingDocument, rows: list[list[str]], page: int, label=DocItemLabel.TABLE):
    cells = [
        TableCell(
            text=value,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
        )
        for r, row in enumerate(rows)
        for c, value in enumerate(row)
    ]
    data = TableData(num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells)
    doc.add_table(data=data, prov=prov(page, 0, 0), label=label)


def test_chunks_never_span_pages():
    doc = DoclingDocument(name="t")
    text(doc, "First page text.", 1)
    text(doc, "Second page text.", 2)
    chunks = chunk_document(doc, max_words=300)
    assert [(c.page, c.content) for c in chunks] == [
        (1, "First page text."),
        (2, "Second page text."),
    ]


def test_long_paragraphs_are_split_to_the_word_limit():
    doc = DoclingDocument(name="t")
    text(doc, " ".join(["word"] * 25), 1)
    chunks = chunk_document(doc, max_words=10)
    assert [len(c.content.split()) for c in chunks] == [10, 10, 5]
    assert [c.chunk_index for c in chunks] == [0, 1, 2]


def test_tables_stay_whole_and_carry_their_heading():
    doc = DoclingDocument(name="t")
    text(doc, "Consolidated Balance Sheets", 3, label=DocItemLabel.SECTION_HEADER)
    table(doc, [["Item", "2018"], ["Total assets", "162,648"]], 3)
    *_, table_chunk = chunk_document(doc, max_words=300)
    assert table_chunk.is_table and table_chunk.page == 3
    assert table_chunk.content.startswith("Consolidated Balance Sheets\n| Item | 2018 |")
    assert "| Total assets | 162,648 |" in table_chunk.content


def test_text_running_across_pages_is_split_by_page():
    doc = DoclingDocument(name="t")
    body = "ends on page one starts on page two"
    doc.add_text(label=DocItemLabel.TEXT, text=body, prov=prov(1, 0, 16))
    doc.texts[-1].prov.append(prov(2, 17, len(body)))
    chunks = chunk_document(doc, max_words=300)
    assert [(c.page, c.content) for c in chunks] == [
        (1, "ends on page one"),
        (2, "starts on page two"),
    ]


def test_table_of_contents_and_page_headers_are_left_out():
    doc = DoclingDocument(name="t")
    text(
        doc,
        "Page 7 | Annual Report",
        1,
        label=DocItemLabel.PAGE_HEADER,
        content_layer=ContentLayer.FURNITURE,
    )
    table(doc, [["Item 7", "Page 30"]], 1, label=DocItemLabel.DOCUMENT_INDEX)
    text(doc, "Real content.", 1)
    assert [c.content for c in chunk_document(doc, max_words=300)] == ["Real content."]
