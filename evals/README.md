# Evaluations

`run_eval.py` runs the five agents on the reference match (`data/reference/match-042.jsonl`) and measures what they
write in three ways. Results go to `results/latest.md` (the README's evaluation table) and `results/latest.json`.

| Measure | What it checks | How |
| --- | --- | --- |
| **Foundry evaluation** | Groundedness against the moment's facts, relevance, coherence, fluency; violence | Built-in Foundry evaluators in a cloud evaluation run in the project (`builtin.groundedness`, …). An LLM judge (`EVAL_JUDGE_DEPLOYMENT`, default the fallback deployment) scores the first four; Foundry's safety model scores violence. The run and its report are visible in the Foundry portal |
| **Code checks** | The checks the API applies before anything airs | `unsourced_numbers` on every English line and card (a number the stats engine never produced); `check_variant` on every Spanish and Hindi version (numbers, names, cites, length, banned topics, actually translated) |
| **Planted errors** | Whether a wrong number would get through | Real lines with one number changed; the code check must catch each one, and the groundedness score on them is reported next to the real lines |

Moments: every goal first, then the most important of the rest (big chances, half time, full time), up to
`--moments` (default 10). Each moment is five model calls through the routers.

```bash
# needs CRQ_OFFLINE=0, the routers and FOUNDRY_PROJECT_ENDPOINT in .env, and the Foundry User role
python evals/run_eval.py                       # 10 moments, Foundry evaluation, writes results/
python evals/run_eval.py --moments 4           # quicker
python evals/run_eval.py --no-foundry          # code checks and planted errors only
```

The agents themselves are registered in Foundry Agent Service with `python -m agents.register_agents`
(`services/agents/agents/register_agents.py`).
