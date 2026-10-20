# Control Room IQ

**An AI operator for the live production control room.**
Built for the Microsoft × Premier League *Inside the Game* Developer Hackathon (October 2026).

Control Room IQ watches a live stream of synthetic football match events, turns them into live
statistics and tactical context, explains *why* a moment matters, proposes what should go on screen
next, and routes every on-air decision through a human operator before it reaches the overlay feed.
The same intelligence is personalized for an analyst, a casual fan, and an accessibility (audio
description) mode, in English, Spanish, Hindi, and Arabic.

> Football is the hackathon's domain. The architecture is a control room story: any environment that
> must turn a live event stream into explainable, auditable operator decisions.

## What it does (the five-stage pipeline)

| Stage | What happens | Where |
| --- | --- | --- |
| Ingest | Synthetic match events (passes, shots, tackles, pressure, possession) stream in at match speed or faster | `services/simulator` → Azure Event Hubs |
| Interpret | Events become match state and statistics: xG, pass networks, pressure index, momentum, player speed/distance thresholds | `services/ingest` on Azure Container Apps, state in Cosmos DB |
| Explain | A tactical explainer agent says why a moment matters (control vs. chaos, pressure shifts, rhythm) with citations to the underlying events | `services/agents` on Microsoft Foundry |
| Render | A studio producer agent proposes the next graphic and on-air line; an operator approves, holds, or overrides; approved items go out as a timed, machine-readable overlay feed | `services/api` + `web` operator console |
| Personalize | The narrator and personalizer agents produce analyst, fan, and accessibility variants in EN/ES/HI/AR | `services/agents` + `web` viewer |

Every narrative is scored for **faithfulness** against the ground-truth event stream using Foundry
evaluations, and every producer decision is logged with its reasoning.

## Microsoft and Azure technologies

Microsoft Foundry (Agent Framework, Foundry Agent Service, model router, evaluations, tracing,
content safety), Azure Event Hubs, Azure Container Apps, Azure Cosmos DB, Azure Logic Apps (approval
workflow), Azure AI Speech (audio description), Azure Monitor / Application Insights, Bicep + Azure
Developer CLI (`azd`), GitHub Actions, GitHub Copilot agent mode.

## Repository layout

```
control-room-iq/
├── services/
│   ├── simulator/   # Synthetic match engine: teams, squads, tactics → event stream (ground truth)
│   ├── ingest/      # Event consumer → match state, statistics, moment detection
│   ├── agents/      # Foundry agents: producer, explainer, narrator, personalizer + orchestration
│   └── api/         # FastAPI: operator console API, WebSocket feeds, overlay feed, approval loop
├── packages/schemas # Shared Pydantic models: events, match state, moments, overlay items
├── web/             # React + TypeScript: operator console and viewer experience
├── evals/           # Foundry evaluation runs and datasets (faithfulness, relevance, safety)
├── infra/           # Bicep modules + azd configuration
├── docs/            # ARCHITECTURE.md, solution description, ADRs, demo script
└── scripts/         # Local dev helpers (PowerShell and bash)
```

## Quick start (local, no Azure required)

```powershell
# Windows PowerShell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m simulator.cli generate --seed 42 --out data/match-001.jsonl   # produce a match
python -m simulator.cli replay data/match-001.jsonl --speed 20           # stream it to stdout
pytest
```

With Azure credentials (`az login`) and `.env` filled from `.env.example`, the same commands
stream to Event Hubs and the agents run on Foundry. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
for the resource list and [docs/SETUP.md](docs/SETUP.md) for provisioning with `azd up`.

## Status

Build week: October 20–27, 2026. See [docs/PLAN.md](docs/PLAN.md) for the day-by-day plan and
owners.

## License

MIT. All data in this repository is synthetic; no real Premier League match data is used or
redistributed. Club, player, and venue names are fictional.
