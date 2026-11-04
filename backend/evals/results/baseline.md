# FilingCite scorecard: baseline

40 FinanceBench questions + 15 should-refuse questions, MIN_SIMILARITY 0.62, top 6 chunks, openai/gpt-oss-120b. Tokens used: 160,790.

| Metric | Result |
| --- | --- |
| Found the right page (evidence in retrieved chunks) | 14/40 (35%) |
| Answered correctly (numeric answers within 1%) | 3/16 (19%) |
| Refused correctly (should-refuse questions) | 15/15 (100%) |
| Blocked a number (number check refusals) | 1 |

## Detail

- Numeric questions answered: 3/16 (19%); correct when answered: 3/3 (100%)
- Written-answer questions answered: 10/24 (42%); answer cited the evidence page: 7/24 (29%)
- FinanceBench refusals by reason: {'not_in_filings': 26, 'unverified_number': 1}

## Number check off vs on

| | Off | On |
| --- | --- | --- |
| FinanceBench answered | 14 | 13 |
| Numeric answers correct | 4 | 3 |
| Numeric answers wrong | 0 | 0 |
| Should-refuse questions answered | 0 | 0 |

Of 1 blocked answers, 1 had a numeric expected answer; 0 of those would have been wrong.

## Refusal threshold sweep (number check on)

| MIN_SIMILARITY | FinanceBench answered | Numeric correct | Refused correctly |
| --- | --- | --- | --- |
| 0.6 | 13/40 | 3/16 | 15/15 |
| 0.61 | 13/40 | 3/16 | 15/15 |
| 0.62 | 13/40 | 3/16 | 15/15 |
| 0.63 | 13/40 | 3/16 | 15/15 |
| 0.64 | 13/40 | 3/16 | 15/15 |
| 0.65 | 13/40 | 3/16 | 15/15 |
| 0.66 | 13/40 | 3/16 | 15/15 |
| 0.67 | 13/40 | 3/16 | 15/15 |
| 0.68 | 13/40 | 3/16 | 15/15 |
| 0.69 | 13/40 | 3/16 | 15/15 |
| 0.7 | 13/40 | 3/16 | 15/15 |
| 0.71 | 13/40 | 3/16 | 15/15 |
| 0.72 | 13/40 | 3/16 | 15/15 |
| 0.73 | 12/40 | 3/16 | 15/15 |
| 0.74 | 12/40 | 3/16 | 15/15 |
| 0.75 | 11/40 | 2/16 | 15/15 |
| 0.76 | 9/40 | 2/16 | 15/15 |
| 0.77 | 7/40 | 1/16 | 15/15 |
| 0.78 | 6/40 | 1/16 | 15/15 |
| 0.79 | 5/40 | 1/16 | 15/15 |
| 0.8 | 5/40 | 1/16 | 15/15 |
