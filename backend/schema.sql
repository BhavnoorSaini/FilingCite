-- Safe to re-run: every statement is IF NOT EXISTS.
-- {embedding_dim} is filled in from the EMBEDDING_DIM environment variable.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per source PDF from FinanceBench.
CREATE TABLE IF NOT EXISTS filings (
    id         bigserial PRIMARY KEY,
    doc_name   text NOT NULL UNIQUE,  -- FinanceBench doc_name, e.g. 3M_2018_10K
    company    text NOT NULL,
    doc_type   text NOT NULL,         -- FinanceBench doc_type, e.g. 10k, 10q
    doc_period integer NOT NULL,      -- fiscal year
    doc_link   text                   -- original filing URL
);

-- One row per chunk. A chunk never spans pages.
CREATE TABLE IF NOT EXISTS chunks (
    id          bigserial PRIMARY KEY,
    filing_id   bigint NOT NULL REFERENCES filings (id) ON DELETE CASCADE,
    page        integer NOT NULL CHECK (page >= 1),  -- 1-based PDF page
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),  -- order within the page
    is_table    boolean NOT NULL DEFAULT false,
    content     text NOT NULL,
    embedding   vector({embedding_dim}) NOT NULL,
    UNIQUE (filing_id, page, chunk_index)
);
