"""Find the chunks most likely to answer a question.

1. If the question names a loaded company (and a year), search only those filings.
2. If it names a financial statement, or a line item that lives on one ("inventory" is on
   the balance sheet, "COGS" on the income statement, "capex" on the cash flow statement),
   put that statement's tables first: these big tables rarely rank well.
3. Add the chunks closest in meaning, each followed by the tables on its page.
4. Keep as many passages as fit the token budget, best first.
"""

import os
import re
from dataclasses import dataclass

import psycopg

from embedding import embed_query
from figures import SHORT_FISCAL_YEAR


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
    similarity: float  # cosine similarity between the question and the chunk


@dataclass(frozen=True)
class Statement:
    asked: re.Pattern  # the statement's name, or a line item found on it
    title: str  # regex for its title on the page (Postgres syntax)
    line_items: tuple[str, ...]  # regexes that all appear in the statement's table


STATEMENTS = (
    Statement(
        re.compile(
            r"balance sheets?|statements? of financial (?:position|condition)"
            r"|total assets|(?:current|total) liabilities|current assets|working capital"
            r"|accounts (?:payable|receivable)|inventor(?:y|ies)|property, plant|PP&E"
            r"|(?:shareholders|stockholders)'? equity",
            re.IGNORECASE,
        ),
        r"balance sheets?|statements? of financial (?:position|condition)",
        (r"total assets", r"total liabilities"),
    ),
    Statement(
        re.compile(
            r"income statements?|statements? of (?:income|operations|earnings)"
            r"|revenues?|net sales|COGS|cost of (?:goods sold|sales|revenue)|gross (?:profit|margin)"
            r"|operating (?:income|margin|profit)|net (?:income|earnings)|EBIT|EPS|per share",
            re.IGNORECASE,
        ),
        r"statements? of (?:consolidated )?(?:income|operations|earnings)(?! and comprehensive)"
        r"|income statements?",
        (r"net (?:income|earnings|loss)", r"per (?:common )?share", r"revenue|net sales|sales"),
    ),
    Statement(
        re.compile(
            r"cash flows?|capital expenditures?|capex|dividends? paid|purchases? of property"
            r"|depreciation and amortization|D&A",
            re.IGNORECASE,
        ),
        r"statements? of (?:consolidated )?cash flows?",
        (r"operating activities", r"investing activities", r"financing activities"),
    ),
)

YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")  # also inside "FY2018"


def normalize(text: str) -> str:
    """Lowercase words separated by single spaces, so "Coca-Cola" matches "coca cola"."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower().replace("&", " and ")))


def years_in(question: str) -> set[int]:
    return {int(y) for y in YEAR.findall(SHORT_FISCAL_YEAR.sub(r" 20\1", question))}


def filings_named(conn: psycopg.Connection, question: str) -> list[int] | None:
    """Filing ids for the companies (and years) the question names, or None to search everything."""
    filings = conn.execute("SELECT id, company, doc_period FROM filings").fetchall()
    asked = f" {normalize(question)} "
    by_company = [f for f in filings if f" {normalize(f[1])} " in asked]
    if not by_company:
        return None
    # A year's figures also appear in the next year's filing, and forecasts in the previous one.
    window = {y + d for y in years_in(question) for d in (-1, 0, 1)}
    by_year = [f for f in by_company if f[2] in window]
    return [f[0] for f in (by_year or by_company)]


def statement_tables(conn: psycopg.Connection, question: str, filings: list[int]) -> list[int]:
    """The tables of each financial statement the question needs, one page per statement.

    A statement page has the statement's title and a table with all its typical line items.
    Among matches, prefer the filing closest to the year asked (the later one on ties, since
    it covers both years), then the earliest page: primary statements come before the notes.
    """
    years = years_in(question)
    tables: list[int] = []
    for statement in STATEMENTS:
        if not statement.asked.search(question):
            continue
        rows = conn.execute(
            """
            SELECT c.id, c.filing_id, f.doc_period, c.page
            FROM chunks c JOIN filings f ON f.id = c.filing_id
            WHERE c.filing_id = ANY(%s) AND c.is_table AND c.content ~* ALL(%s)
              AND EXISTS (SELECT 1 FROM chunks t WHERE t.filing_id = c.filing_id
                          AND t.page = c.page AND left(t.content, 200) ~* %s)
            ORDER BY c.chunk_index
            """,
            (filings, list(statement.line_items), statement.title),
        ).fetchall()
        if rows:
            gap = lambda r: min((abs(r[2] - y) for y in years), default=0)
            best = min(rows, key=lambda r: (gap(r), -r[2], r[3]))
            tables += [r[0] for r in rows if (r[1], r[3]) == (best[1], best[3])]
    return tables


def search(conn: psycopg.Connection, question: str, k: int) -> list[Passage]:
    """The best passages for the question, best first, within the token budget."""
    vector = embed_query(question)
    filings = filings_named(conn, question)
    statements = statement_tables(conn, question, filings) if filings else []
    # Exact nearest neighbours (no approximate index): fast enough at this size.
    nearest = [
        row[0]
        for row in conn.execute(
            """
            SELECT id FROM chunks
            WHERE (%(filings)s::bigint[] IS NULL OR filing_id = ANY(%(filings)s))
              AND id <> ALL(%(statements)s)
            ORDER BY embedding <=> %(v)s LIMIT %(k)s
            """,
            {"filings": filings, "statements": statements, "v": vector, "k": k},
        )
    ]
    ordered = statements + with_page_tables(conn, nearest, set(statements))
    return within_budget(fetch(conn, ordered, vector), int(os.environ["CONTEXT_TOKEN_BUDGET"]))


def with_page_tables(conn: psycopg.Connection, nearest: list[int], skip: set[int]) -> list[int]:
    """Put up to PAGE_TABLES_MAX other tables from the nearest chunks' pages after each chunk."""
    rows = conn.execute(
        """
        SELECT c.id, t.id FROM chunks c
        JOIN chunks t ON t.filing_id = c.filing_id AND t.page = c.page AND t.is_table
        WHERE c.id = ANY(%s) ORDER BY t.chunk_index
        """,
        (nearest,),
    ).fetchall()
    left = int(os.environ["PAGE_TABLES_MAX"])
    seen = set(nearest) | skip
    ordered: list[int] = []
    for chunk_id in nearest:
        ordered.append(chunk_id)
        for source, table_id in rows:
            if source == chunk_id and table_id not in seen and left > 0:
                ordered.append(table_id)
                seen.add(table_id)
                left -= 1
    return ordered


def within_budget(passages: list[Passage], budget: int) -> list[Passage]:
    """Keep passages in rank order while their text fits the token budget (about 4 chars a token).

    The free Groq tier allows 8K tokens a minute, so one oversized prompt would be rejected.
    """
    kept: list[Passage] = []
    used = 0
    for p in passages:
        tokens = len(p.content) // 4
        if not kept or used + tokens <= budget:
            kept.append(p)
            used += tokens
    return kept


def fetch(conn: psycopg.Connection, ids: list[int], vector) -> list[Passage]:
    """Load chunks by id, keeping the given order."""
    rows = conn.execute(
        """
        SELECT c.id, f.doc_name, f.company, f.doc_type, f.doc_period, f.doc_link,
               c.page, c.is_table, c.content, 1 - (c.embedding <=> %(v)s)
        FROM chunks c JOIN filings f ON f.id = c.filing_id
        WHERE c.id = ANY(%(ids)s)
        """,
        {"v": vector, "ids": ids},
    ).fetchall()
    by_id = {row[0]: Passage(*row) for row in rows}
    return [by_id[i] for i in ids]
