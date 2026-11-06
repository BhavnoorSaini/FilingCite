# FilingCite

[![CI](https://github.com/BhavnoorSaini/FilingCite/actions/workflows/ci.yml/badge.svg)](https://github.com/BhavnoorSaini/FilingCite/actions/workflows/ci.yml)

Ask a question about a public company's SEC filings and get an answer that cites the exact
page it came from. If FilingCite can't trace every number to a cited page, it says "I don't
know" instead.

AI models make up numbers, and in finance one wrong figure ruins an answer. So the model may
only use numbers printed on the pages it cites, and it never does the math itself: it names
the calculation and Python does it.

Live: [filingcite.vercel.app](https://filingcite.vercel.app)

![FilingCite answering a margin question with its calculation and source, then refusing a stock prediction](docs/demo.gif)

## How well it works

Graded by Python on the 150 open-source [FinanceBench](https://github.com/patronus-ai/financebench)
questions, plus 15 it should refuse ([full results](backend/evals/results/full.md)):

| Metric | Result |
| --- | --- |
| Found the right page | 102/150 (68%) |
| Answered correctly (numeric answers within 1%) | 44/54 (81%) |
| Refused correctly | 15/15 (100%) |
| Blocked a number | 6 |

Only the 54 questions with a short numeric answer are marked right or wrong. The other 96
have written answers that need a person to judge.

Turning the number check off shows what it does:

| Number check | Off | On |
| --- | --- | --- |
| Questions answered | 108 | 102 |
| Numeric answers correct | 46 | 44 |
| Numeric answers wrong | 2 | 2 |

The model rarely makes up a figure outright, so the check doesn't raise accuracy. In this run
it stopped no wrong numeric answers and blocked two right ones (MGM and Walmart, below). What
it buys is a guarantee: every number you see is on a cited page.

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
4. **Check** ([answer.py](backend/answer.py)): refuse if the reply is malformed, cites an
   excerpt it wasn't given, or uses a number that isn't on a cited page. Then Python runs the
   calculations, rounds them the way the question asks, and fills in the results.

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
- The number check can't tell a real number from the right one, and it can't check answers
  with no numbers.
- Companies are found by name or official ticker ("JPM", "JnJ"), but not by nicknames like
  "AMEX".
- A figure from the question can only appear in the answer if a calculation used it, so
  phrases like "3-year" or "over 20%" block some correct answers.
- Zero is always blocked, because filings print a dash instead of 0.
- The live site runs on Groq's free tier, so it can fail under heavy use. The free tier also
  caps each reply, reasoning included, at 4,096 tokens. Long multi-step questions sometimes
  run out and get refused; at 8,192 most of them pass.

## Three real wrong answers

1. **Pfizer's remaining Upjohn spin-off cost: $700 million (expected $77.78 million).**
   Retrieval found the 2021 10-K instead of the 2023 10-Q, and the model quoted the total
   cost instead of what was left to pay. The 10-Q says about 90% of $700 million has been
   spent, which leaves $70 million, so the expected answer looks wrong too.
2. **MGM's 3-year average capex as a % of revenue: right (7.9%), but blocked.** Python worked
   out each year's share and the average, then the model wrote "The 3-year average". That 3
   came from the question, and a figure from the question isn't evidence, so the whole answer
   was refused.
3. **Walmart's 3-year average EBITDA margin: right (6.2%), but blocked.** The model added up
   operating income and D&A for each year in its head and passed the totals (like 31,555) to
   Python as if they were on a page. They weren't, so the check refused it. The model isn't
   allowed to do arithmetic, even when it gets it right.
