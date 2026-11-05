# FilingCite scorecard: full

150 FinanceBench + 15 should-refuse questions, MIN_SIMILARITY 0.62, openai/gpt-oss-120b.

| Metric | Result |
| --- | --- |
| Found the right page | 94/150 (63%) |
| Answered correctly (numeric, within 1%) | 42/54 (78%) |
| Refused correctly | 15/15 (100%) |
| Blocked a number | 4 |

## Number check off vs on

| | Off | On |
| --- | --- | --- |
| FinanceBench answered | 100 | 97 |
| Numeric answers correct | 42 | 42 |
| Numeric answers wrong | 5 | 4 |

## Refusal threshold sweep

| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |
| --- | --- | --- | --- |
| 0.6 | 97 | 42 | 15/15 |
| 0.62 | 97 | 42 | 15/15 |
| 0.64 | 97 | 42 | 15/15 |
| 0.66 | 97 | 42 | 15/15 |
| 0.68 | 95 | 42 | 15/15 |
| 0.7 | 92 | 42 | 15/15 |
| 0.72 | 89 | 40 | 15/15 |
| 0.74 | 82 | 39 | 15/15 |
| 0.76 | 57 | 26 | 15/15 |
| 0.78 | 32 | 9 | 15/15 |
| 0.8 | 17 | 3 | 15/15 |
