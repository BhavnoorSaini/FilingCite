# FilingCite

[![CI](https://github.com/BhavnoorSaini/FilingCite/actions/workflows/ci.yml/badge.svg)](https://github.com/BhavnoorSaini/FilingCite/actions/workflows/ci.yml)

Ask a question about a public company's SEC filings and get an answer that cites the exact
page it came from. If the filings don't support an answer, FilingCite says "I don't know".

AI models are bad at arithmetic, and in finance one wrong figure ruins an answer. So the
model never does the math itself: it names the calculation and Python does it, and every
answer links to the pages it used.

Live: [filingcite.vercel.app](https://filingcite.vercel.app)

![FilingCite answering a margin question with its calculation and source, then refusing a stock prediction](docs/demo.gif)

## How well it works

Graded by Python on the 150 open-source [FinanceBench](https://github.com/patronus-ai/financebench)
questions, plus 15 it should refuse ([full results](backend/evals/results/full.md)):

| Metric | Result |
| --- | --- |
| Found the right page | 102/150 (68%) |
| Answered correctly (numeric answers within 1%) | 48/54 (89%) |
| Refused correctly | 15/15 (100%) |

Only the 54 questions with a short numeric answer are marked right or wrong: 48 right, 3
wrong and 3 refused. The other 96 have written answers that need a person to judge.

## How it works

1. **Ingest, once on a Mac** ([backend/ingest](backend/ingest)): Docling turns each PDF into
   text and tables with page numbers. Text is split into ~300-word chunks that never cross a
   page, and tables stay whole. FastEmbed (bge-small-en-v1.5) embeds them into Neon Postgres
   with pgvector.
2. **Retrieve** ([retrieval.py](backend/retrieval.py)): search only the filings of the company
   (by name or ticker) and year in the question. If the question needs a financial statement,
   say for capex or inventory, that statement's table goes first, then the chunks closest in
   meaning.
3. **Draft** ([llm.py](backend/llm.py)): if even the best chunk is a weak match, refuse.
   Otherwise gpt-oss-120b on Groq replies in strict JSON with the answer, the excerpts it
   cites, the numbers it used and any calculations.
4. **Check** ([answer.py](backend/answer.py)): refuse if the reply is malformed or cites an
   excerpt it wasn't given. Then Python runs the calculations, rounds them the way the
   question asks, and fills in the results.

## Run it yourself

You'll need Python 3.12 with uv, Node with pnpm, the Vercel CLI, a Neon database, a Groq API
key and a clone of the FinanceBench repo.

```bash
cp .env.example .env   # fill in DATABASE_URL, LLM_API_KEY and FINANCEBENCH_DIR
cd backend
uv sync
uv run --env-file ../.env python -m scripts.init_db
uv run --group ingest --env-file ../.env python -m ingest.load   # takes hours; resumable
cd ../frontend && pnpm install && cd ..
vercel dev   # http://localhost:3000
```

The tests use a fake model and no network. The eval picks up where it stopped if it's
interrupted:

```bash
cd backend
uv run pytest
uv run --env-file ../.env python -m evals.run --name full
uv run --env-file ../.env python -m evals.score --name full
```

## Known limits

- Retrieval misses the evidence page for 32% of questions, mostly narrative ones answered
  deep in the MD&A text.
- Nothing checks that an answer's numbers appear on the cited pages; the citations are
  there so you can check them yourself.
- Companies are found by name or official ticker ("JPM", "JnJ"), but not by nicknames like
  "AMEX".
- The live site runs on Groq's free tier, so it can fail under heavy use. The free tier also
  caps each reply, reasoning included, at 4,096 tokens. Long multi-step questions sometimes
  run out and get refused; at 8,192 most of them pass.

## Three real wrong answers

1. **PepsiCo's credit facility increase: $750 million (expected $400 million).** The 8-K says
   the new $4.2 billion five-year facility *may later be increased* to $4.95 billion. The
   model subtracted those two, mistaking an optional upsize for the change. The real change
   is from the $3.8 billion facility it replaced, which was in the same excerpts.
2. **Pfizer's remaining Upjohn spin-off cost: $700 million (expected $77.78 million).**
   Retrieval found the 2021 10-K instead of the 2023 10-Q, and the model quoted the total
   cost instead of what was left to pay. The 10-Q says about 90% of $700 million has been
   spent, which leaves $70 million, so the expected answer looks wrong too.
3. **American Water Works' FY2020 dividends: $0.389 billion (expected $0.40 billion).** The
   answer matches the "Dividends paid" line on the cash flow statement ($389 million), but
   it's 3% off the expected answer, outside the 1% tolerance.
