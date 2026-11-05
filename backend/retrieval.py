"""Find the chunks most likely to answer a question.

1. If the question names a loaded company (and a year), search only those filings.
2. If it names a financial statement, or a line item that lives on one ("inventory" is on
   the balance sheet, "COGS" on the income statement, "capex" on the cash flow statement),
   put that statement's tables first: these big tables rarely rank well.
3. Add the chunks closest in meaning.
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
    doc_name: str
    company: str
    doc_type: str
    doc_period: int
    doc_link: str | None
    page: int
    content: str
    similarity: float  # cosine similarity between the question and the chunk


@dataclass(frozen=True)
class Statement:
    title: str  # how the statement is titled on its page
    line_items: list[str]  # all of these appear in the statement's own table
    asked_as: list[str]  # other words in a question that mean this statement is needed

    def is_asked(self, question: str) -> bool:
        return bool(re.search("|".join([self.title, *self.asked_as]), question, re.IGNORECASE))


# Patterns work in both Python and Postgres.
STATEMENTS = [
    Statement(  # balance sheet
        title=r"balance sheets?|statements? of financial (?:position|condition)",
        line_items=["total assets", "total liabilities"],
        asked_as=[
            "total assets",
            "(?:current|total) liabilities",
            "current assets",
            "working capital",
            "accounts (?:payable|receivable)",
            "inventor(?:y|ies)",
            "property, plant",
            "PP&E",
            "(?:shareholders|stockholders)'? equity",
        ],
    ),
    Statement(  # income statement
        title=r"statements? of (?:consolidated )?(?:income|operations|earnings)(?! and comprehensive)"
        r"|income statements?",
        line_items=[
            "net (?:income|earnings|loss)",
            "per (?:common )?share",
            "revenue|net sales|sales",
        ],
        asked_as=[
            "revenues?",
            "net sales",
            "COGS",
            "cost of (?:goods sold|sales|revenue)",
            "gross (?:profit|margin)",
            "operating (?:income|margin|profit)",
            "net (?:income|earnings)",
            "EBIT",
            "EPS",
            "per share",
        ],
    ),
    Statement(  # cash flow statement
        title=r"statements? of (?:consolidated )?cash flows?",
        line_items=["operating activities", "investing activities", "financing activities"],
        asked_as=[
            "cash flows?",
            "capital expenditures?",
            "capex",
            "dividends? paid",
            "purchases? of property",
            "depreciation and amortization",
            "D&A",
        ],
    ),
]

YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")  # also inside "FY2018"


def normalize(text: str) -> str:
    """Lowercase words separated by single spaces, so "Coca-Cola" matches "coca cola"."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower().replace("&", " and ")))


def years_in(question: str) -> set[int]:
    return {int(y) for y in YEAR.findall(SHORT_FISCAL_YEAR.sub(r" 20\1", question))}


def filings_named(conn: psycopg.Connection, question: str) -> list[int] | None:
    """Filing ids for the companies (and years) the question names, or None to search everything."""
    asked = f" {normalize(question)} "
    named = [
        (filing_id, period)
        for filing_id, company, period in conn.execute(
            "SELECT id, company, doc_period FROM filings"
        )
        if f" {normalize(company)} " in asked
    ]
    if not named:
        return None
    # A year's figures also appear in the next year's filing, and forecasts in the previous one.
    years = {y + d for y in years_in(question) for d in (-1, 0, 1)}
    in_years = [filing_id for filing_id, period in named if period in years]
    return in_years or [filing_id for filing_id, _ in named]


def statement_tables(conn: psycopg.Connection, question: str, filings: list[int]) -> list[int]:
    """The tables of each financial statement the question needs, one page per statement.

    A statement page has the statement's title and a table with all its typical line items.
    Among matches, prefer the filing closest to the year asked (the later one on ties, since
    it covers both years), then the earliest page: primary statements come before the notes.
    """
    years = years_in(question)

    def preference(row):
        _, _, period, page = row
        distance = min((abs(period - y) for y in years), default=0)
        return distance, -period, page

    tables: list[int] = []
    for statement in STATEMENTS:
        if not statement.is_asked(question):
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
            (filings, statement.line_items, statement.title),
        ).fetchall()
        if rows:
            _, filing, _, page = min(rows, key=preference)
            tables += [row[0] for row in rows if (row[1], row[3]) == (filing, page)]
    return tables


def search(conn: psycopg.Connection, question: str, k: int) -> list[Passage]:
    """The best passages for the question, best first, within the token budget."""
    vector = embed_query(question)
    filings = filings_named(conn, question)
    statements = statement_tables(conn, question, filings) if filings else []
    # Exact nearest neighbours (no approximate index): fast enough at this size.
    nearest = conn.execute(
        """
        SELECT id FROM chunks
        WHERE (%(filings)s::bigint[] IS NULL OR filing_id = ANY(%(filings)s))
          AND id <> ALL(%(statements)s)
        ORDER BY embedding <=> %(v)s LIMIT %(k)s
        """,
        {"filings": filings, "statements": statements, "v": vector, "k": k},
    ).fetchall()
    passages = fetch(conn, statements + [row[0] for row in nearest], vector)
    return within_budget(passages, int(os.environ["CONTEXT_TOKEN_BUDGET"]))


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
               c.page, c.content, 1 - (c.embedding <=> %(v)s)
        FROM chunks c JOIN filings f ON f.id = c.filing_id
        WHERE c.id = ANY(%(ids)s)
        """,
        {"v": vector, "ids": ids},
    ).fetchall()
    by_id = {row[0]: Passage(*row[1:]) for row in rows}
    return [by_id[i] for i in ids]
