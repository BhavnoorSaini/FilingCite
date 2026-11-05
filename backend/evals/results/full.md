# FilingCite scorecard: full

150 FinanceBench + 15 should-refuse questions, MIN_SIMILARITY 0.62, openai/gpt-oss-120b.

| Metric | Result |
| --- | --- |
| Found the right page | 93/150 (62%) |
| Answered correctly (numeric, within 1%) | 40/54 (74%) |
| Refused correctly | 15/15 (100%) |
| Blocked a number | 6 |

Numeric answers shown: 46, of which correct: 40/46 (87%). Written answers that cited the evidence page: 29/96 (30%).

## Number check off vs on

| | Off | On |
| --- | --- | --- |
| FinanceBench answered | 105 | 99 |
| Numeric answers correct | 40 | 40 |
| Numeric answers wrong | 7 | 6 |

## Refusal threshold sweep

| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |
| --- | --- | --- | --- |
| 0.6 | 99 | 40 | 15/15 |
| 0.62 | 99 | 40 | 15/15 |
| 0.64 | 99 | 40 | 15/15 |
| 0.66 | 99 | 40 | 15/15 |
| 0.68 | 97 | 40 | 15/15 |
| 0.7 | 94 | 40 | 15/15 |
| 0.72 | 91 | 39 | 15/15 |
| 0.74 | 82 | 37 | 15/15 |
| 0.76 | 58 | 25 | 15/15 |
| 0.78 | 32 | 9 | 15/15 |
| 0.8 | 17 | 3 | 15/15 |
