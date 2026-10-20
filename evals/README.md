# Evaluations

`run_eval.py` (to be added day 3) replays a match offline, collects every (moment, explanation, line,
variants) tuple into `datasets/<match>.jsonl`, and submits a Foundry evaluation run via
`azure-ai-projects` with: groundedness/faithfulness against the cited events and state snapshot,
relevance, fluency per language (en/es/hi/ar), and content safety. Scores are written back to the
`evaluations` Cosmos container and surfaced on the operator console per proposal.
