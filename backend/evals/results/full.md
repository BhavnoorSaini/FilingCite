# FilingCite scorecard: full

150 FinanceBench + 15 should-refuse questions, MIN_SIMILARITY 0.62, openai/gpt-oss-120b.

| Metric | Result |
| --- | --- |
| Found the right page | 102/150 (68%) |
| FinanceBench questions answered | 113/150 |
| Answered correctly (numeric, within 1%) | 48/54 (89%) |
| Numeric answers wrong | 3 |
| Refused correctly | 15/15 (100%) |

## Refusal threshold sweep

| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |
| --- | --- | --- | --- |
| 0.6 | 113 | 48 | 15/15 |
| 0.62 | 113 | 48 | 15/15 |
| 0.64 | 113 | 48 | 15/15 |
| 0.66 | 113 | 48 | 15/15 |
| 0.68 | 111 | 48 | 15/15 |
| 0.7 | 107 | 48 | 15/15 |
| 0.72 | 103 | 46 | 15/15 |
| 0.74 | 92 | 43 | 15/15 |
| 0.76 | 66 | 30 | 15/15 |
| 0.78 | 37 | 9 | 15/15 |
| 0.8 | 18 | 3 | 15/15 |
