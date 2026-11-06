# FilingCite scorecard: full

150 FinanceBench + 15 should-refuse questions, MIN_SIMILARITY 0.62, openai/gpt-oss-120b.

| Metric | Result |
| --- | --- |
| Found the right page | 94/150 (63%) |
| Answered correctly (numeric, within 1%) | 43/54 (80%) |
| Refused correctly | 15/15 (100%) |
| Blocked a number | 2 |

## Number check off vs on

| | Off | On |
| --- | --- | --- |
| FinanceBench answered | 100 | 98 |
| Numeric answers correct | 43 | 43 |
| Numeric answers wrong | 4 | 4 |

## Refusal threshold sweep

| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |
| --- | --- | --- | --- |
| 0.6 | 98 | 43 | 15/15 |
| 0.62 | 98 | 43 | 15/15 |
| 0.64 | 98 | 43 | 15/15 |
| 0.66 | 98 | 43 | 15/15 |
| 0.68 | 96 | 43 | 15/15 |
| 0.7 | 93 | 43 | 15/15 |
| 0.72 | 90 | 42 | 15/15 |
| 0.74 | 82 | 40 | 15/15 |
| 0.76 | 57 | 27 | 15/15 |
| 0.78 | 31 | 10 | 15/15 |
| 0.8 | 17 | 4 | 15/15 |
