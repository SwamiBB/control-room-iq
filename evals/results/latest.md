# Evaluation results

Run 2026-10-26 18:59 UTC on `match-042.jsonl`: 10 moments, 50 model-written outputs (routers at `reasoning_effort=low`). Judge for groundedness, relevance, coherence and fluency: `gpt-4.1-mini`; violence uses Foundry's safety model. Scores are 1–5 (higher is better), except violence, where lower is safer (0–7).

| Output | groundedness | relevance | coherence | fluency | violence |
| --- | --- | --- | --- | --- | --- |
| card/en | 4.30 (n=10) | 4.80 (n=10) | 4.00 (n=10) | 2.70 (n=10) | 0.20 (n=10) |
| explanation/en | 4.60 (n=10) | 4.80 (n=10) | 3.70 (n=10) | 3.60 (n=10) | 0.00 (n=10) |
| line/en | 3.60 (n=10) | 5.00 (n=10) | 4.10 (n=10) | 3.00 (n=10) | 0.20 (n=10) |
| planted | 2.00 (n=10) | 5.00 (n=10) | 4.10 (n=10) | 2.90 (n=10) | 0.40 (n=10) |
| variant/es | 4.10 (n=10) | 5.00 (n=10) | 4.10 (n=10) | 3.10 (n=10) | 1.00 (n=10) |
| variant/hi | 4.20 (n=10) | 5.00 (n=10) | 4.40 (n=10) | 3.20 (n=10) | 0.00 (n=10) |

The full run, with every output and score, is in the Foundry project under Evaluations.

## Code checks (the API applies these before anything airs)

- English lines and cards with a number the stats engine never produced: **4 of 20** (flagged to the operator).
- Spanish and Hindi versions that pass every check: **0 of 20**; failures by check: {'names': 14, 'length': 20, 'numbers': 6}. A version that fails is replaced by the template line in that language.

## Planted errors

- Real lines with one number changed: **7 of 10 caught** by the code check. Missed: ['Leo Hart shoots wide — 0.7 xG, 85.3 km/h', 'Nik Gale fires wide — 0.7 xG, 105.9 km/h', 'Kai Reed denied on Har’s top chance — 0.8 xG, 98 km/h']
- Groundedness on the planted lines: **2.00**, for comparison with the real lines above.
