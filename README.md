# FilingCite

[![CI](https://github.com/BhavnoorSaini/FilingCite/actions/workflows/ci.yml/badge.svg)](https://github.com/BhavnoorSaini/FilingCite/actions/workflows/ci.yml)

Ask questions about public companies' SEC filings. Every number in an answer is traced to a
cited page, or FilingCite says "I don't know".

AI models invent numbers, and in finance one wrong figure makes an answer worthless. So the
model may only quote numbers that are on the pages it cites, and it never does arithmetic: it
names the calculation and Python does it.

Live: [filingcite.vercel.app](https://filingcite.vercel.app)

![FilingCite answering a margin question with its calculation and source, then refusing a stock prediction](docs/demo.gif)

## Scorecard

The 150 [FinanceBench](https://github.com/patronus-ai/financebench) open-source questions plus
15 that should be refused, graded by Python ([full results](backend/evals/results/full.md)):

| Metric | Result |
| --- | --- |
| Found the right page | 102/150 (68%) |
| Answered correctly (numeric answers within 1%) | 44/54 (81%) |
| Refused correctly | 15/15 (100%) |
| Blocked a number | 6 |

Only the 54 short numeric answers are graded; the 96 written ones need judgement.

| Number check | Off | On |
| --- | --- | --- |
| Questions answered | 108 | 102 |
| Numeric answers correct | 46 | 44 |
| Numeric answers wrong | 2 | 2 |

The model rarely invents a figure outright, so the check mostly guarantees that every number
shown is traceable. In this run it stopped no wrong numeric answers and blocked two correct
ones (MGM and Walmart, below): its value is the guarantee, not accuracy.

## How it works

1. **Ingest, once on a Mac** ([backend/ingest](backend/ingest)): Docling reads each PDF into
   text and tables with page numbers. Text becomes ~300-word chunks that never cross a page;
   tables stay whole. FastEmbed (bge-small-en-v1.5) embeds them into Neon Postgres with pgvector.
2. **Retrieve** ([retrieval.py](backend/retrieval.py)): search the filings of the company (by name
   or ticker) and year the question names. If it names a financial statement or a line item
   on one, put that statement's table first, then the closest chunks by meaning.
3. **Draft** ([llm.py](backend/llm.py)): if even the best chunk is a weak match, refuse.
   Otherwise gpt-oss-120b on Groq replies in strict JSON: the answer, the excerpts it cites, the
   numbers it used, and any calculations.
4. **Check** ([answer.py](backend/answer.py)): refuse if the reply is malformed, cites an
   excerpt it wasn't given, or uses a number that isn't on a cited page. Python runs the
   calculations, rounds them as the question asks, and fills in the results.

## Quickstart

Needs Python 3.12 with uv, Node with pnpm, the Vercel CLI, a Neon database, a Groq API key and
a clone of the FinanceBench repo.

```bash
cp .env.example .env   # fill in DATABASE_URL, LLM_API_KEY and FINANCEBENCH_DIR
cd backend
uv sync
uv run --env-file ../.env python -m scripts.init_db
uv run --group ingest --env-file ../.env python -m ingest.load   # takes hours; resumable
cd ../frontend && pnpm install && cd ..
vercel dev   # http://localhost:3000
```

Tests (fake model, no network) and the eval (resumable):

```bash
cd backend
uv run pytest
uv run --env-file ../.env python -m evals.run --name full
uv run --env-file ../.env python -m evals.score --name full
```

## Cuts

No stock predictions or investment advice, live prices, comparisons across companies, user
uploads, accounts, or filings outside FinanceBench.

## Known limits

- Retrieval misses 32% of evidence pages, mostly for narrative questions answered in long
  MD&A text.
- The number check can't catch a wrong choice of real numbers, or answers with no numbers.
- Companies are matched by name or official ticker ("JPM", "JnJ"), so nicknames like
  "AMEX" search every filing.
- Figures from the question can only appear in the answer if a calculation used them, so
  phrases like "3-year" or "over 20%" block some correct answers.
- Zero is always blocked, since filings print a dash instead.
- The live site uses Groq's free tier, so it can fail under load. Its limits also cap a reply,
  reasoning included, at 4,096 tokens; long multi-step questions sometimes run out and are
  refused (with 8,192 they mostly pass).

## Three real wrong answers

1. **Pfizer's remaining Upjohn spin-off cost: $700 million (expected $77.78 million).**
   Retrieval returned the 2021 10-K instead of the 2023 10-Q, and the model quoted the total
   cost rather than what was left to pay. The 10-Q says about 90% of $700 million has been
   spent, which leaves $70 million, so the expected answer looks wrong too.
2. **MGM's 3-year average capex as a % of revenue: correct (7.9%), but blocked.** Python
   worked out each year's share and the average, then the model wrote "The 3-year average".
   The 3 came from the question, and figures from the question aren't evidence, so the whole
   answer was refused.
3. **Walmart's 3-year average EBITDA margin: correct (6.2%), but blocked.** The model added
   operating income and D&A for each year itself and passed the sums (like 31,555) to Python
   as if they were on a page. They weren't, so the check refused it: the model may not do
   arithmetic, even when it gets it right.
