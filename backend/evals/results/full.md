# FilingCite scorecard: full

150 FinanceBench + 15 should-refuse questions, MIN_SIMILARITY 0.62, openai/gpt-oss-120b.

| Metric | Result |
| --- | --- |
| Found the right page | 102/150 (68%) |
| Answered correctly (numeric, within 1%) | 44/54 (81%) |
| Refused correctly | 15/15 (100%) |
| Blocked a number | 6 |

## Number check off vs on

| | Off | On |
| --- | --- | --- |
| FinanceBench answered | 108 | 102 |
| Numeric answers correct | 46 | 44 |
| Numeric answers wrong | 2 | 2 |

## Refusal threshold sweep

| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |
| --- | --- | --- | --- |
| 0.6 | 102 | 44 | 15/15 |
| 0.62 | 102 | 44 | 15/15 |
| 0.64 | 102 | 44 | 15/15 |
| 0.66 | 102 | 44 | 15/15 |
| 0.68 | 100 | 44 | 15/15 |
| 0.7 | 96 | 44 | 15/15 |
| 0.72 | 92 | 42 | 15/15 |
| 0.74 | 83 | 40 | 15/15 |
| 0.76 | 62 | 30 | 15/15 |
| 0.78 | 33 | 9 | 15/15 |
| 0.8 | 17 | 4 | 15/15 |
