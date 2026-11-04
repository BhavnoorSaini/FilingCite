from dataclasses import dataclass

import psycopg

from embedding import embed_query


@dataclass
class Passage:
    chunk_id: int
    doc_name: str
    company: str
    doc_type: str
    doc_period: int
    doc_link: str | None
    page: int
    is_table: bool
    content: str
    similarity: float


def search(conn: psycopg.Connection, question: str, k: int) -> list[Passage]:
    """The k chunks closest in meaning to the question, best first."""
    vector = embed_query(question)
    rows = conn.execute(
        """
        SELECT c.id, f.doc_name, f.company, f.doc_type, f.doc_period, f.doc_link,
               c.page, c.is_table, c.content, 1 - (c.embedding <=> %(v)s) AS similarity
        FROM chunks c JOIN filings f ON f.id = c.filing_id
        ORDER BY c.embedding <=> %(v)s
        LIMIT %(k)s
        """,
        {"v": vector, "k": k},
    ).fetchall()
    return [Passage(*row) for row in rows]
