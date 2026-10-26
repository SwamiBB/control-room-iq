# Evaluation results

Run 2026-10-26 21:20 UTC on `match-042.jsonl`: 10 moments, 50 model-written outputs (routers at `reasoning_effort=low`). Judge for groundedness, relevance, coherence and fluency: `gpt-4.1-mini`; violence uses Foundry's safety model. Scores are 1–5 (higher is better), except violence, where lower is safer (0–7).

| Output | groundedness | relevance | coherence | fluency | violence |
| --- | --- | --- | --- | --- | --- |
| card/en | 4.40 (n=10) | 4.70 (n=10) | 3.90 (n=10) | 2.50 (n=10) | 0.20 (n=10) |
| explanation/en | 4.60 (n=10) | 4.80 (n=10) | 3.80 (n=10) | 3.30 (n=10) | 0.00 (n=10) |
| line/en | 3.80 (n=10) | 5.00 (n=10) | 4.00 (n=10) | 2.90 (n=10) | 0.40 (n=10) |
| planted (absent) | 2.00 (n=5) | 5.00 (n=5) | 4.00 (n=5) | 2.80 (n=5) | 0.40 (n=5) |
| planted (swapped) | 2.00 (n=5) | 4.60 (n=5) | 3.80 (n=5) | 2.40 (n=5) | 1.20 (n=5) |
| variant/es | 4.20 (n=10) | 5.00 (n=10) | 4.10 (n=10) | 2.90 (n=10) | 1.20 (n=10) |
| variant/hi | 4.00 (n=10) | 5.00 (n=10) | 4.00 (n=10) | 2.80 (n=10) | 0.20 (n=10) |

The full run, with every output and score, is in the Foundry project under Evaluations.

## Code checks (the API applies these before anything airs)

- English lines and cards with a number the stats engine never produced: **5 of 20** (flagged to the operator).
- Spanish and Hindi versions that pass every check: **20 of 20**; failures by check: none. A version that fails is replaced by the template line in that language.

## Planted errors (real lines with one number changed)

- **A number the match data doesn't contain:** 5 of 5 caught by the code check.
- **A real number from the wrong place** (another team's xG, a different count): 0 of 5 caught by the code check, which accepts any number the data contains; this is the case the groundedness judge is for.
- Groundedness on the planted (absent) lines: **2.00**, against the real lines above.
- Groundedness on the planted (swapped) lines: **2.00**, against the real lines above.
