# Architecture

Status: draft v0.1, October 20, 2026. Owner: AI CoE lead. Target region: **East US 2**.

## 1. System overview

```
 Match simulator ──▶ Event Hubs ──▶ Ingest & stats (Container Apps) ──▶ Cosmos DB (match state, moments)
      (ACA job)        (crq-events)        │                                   │
                                           ▼                                   ▼
                              Moment detector emits "moments" ──▶ Foundry agents (Agent Framework)
                                                                   producer · explainer · narrator · personalizer
                                                                       │
                                                                       ▼
                                           API (Container Apps, FastAPI) ◀──▶ Operator console (React)
                                             │  approve / hold / override         │
                                             ▼                                    ▼
                                      Overlay feed (timed JSON, WebSocket + Event Hubs crq-overlay)
                                             │
                                             ▼
                                      Viewer experience (React): analyst · fan · accessibility, EN/ES/HI/AR
```

Cross-cutting: Foundry evaluations (faithfulness, relevance, safety) run on every narrative; OpenTelemetry
traces from every service flow to Application Insights; Logic Apps implements the approval SLA (auto-hold if
an operator does not act within N seconds); Azure AI Speech produces audio description for the accessibility
mode.

## 2. Components

### 2.1 Simulator (`services/simulator`)
A deterministic, seedable match engine. Given two fictional squads and tactical profiles, it produces a
football-realistic event stream for 90+ minutes: passes (with origin/destination coordinates, distance,
difficulty), carries, shots (with xG), tackles, interceptions, fouls, set pieces, possession changes,
pressure events, substitutions, cards, and match metadata. Output is JSONL conforming to
`packages/schemas` (`MatchEvent`). It can write to a file, stdout, or Event Hubs, at 1× to 100× speed.
A separate **squad authoring agent** (Foundry) can generate teams, squads, and storylines that seed the
engine, which satisfies the "data innovation" requirement while keeping ground truth deterministic.

### 2.2 Ingest and statistics (`services/ingest`)
An Event Hubs consumer (Container App, KEDA-scaled on partition lag) that folds events into `MatchState`:
score, possession %, pass completion, pass networks, xG per team/player, pressure index per 5-minute window,
momentum, player distance and speed with threshold triggers. It persists state snapshots and raises
`Moment` records (goal, big chance, momentum shift, pressure spike, milestone) into Cosmos DB and onto the
`crq-moments` Event Hub.

### 2.3 Agents (`services/agents`)
Built with the Microsoft Agent Framework (`agent-framework` 1.22+, `agent-framework-foundry`), hosted via
Foundry Agent Service, orchestrated as a workflow with shared state:

| Agent | Role | Model (via model router, routing mode) | Output |
| --- | --- | --- | --- |
| Tactical explainer | Why a moment matters; cites event IDs | Quality (reasoning-capable) | `Explanation` |
| Narrator | On-air lines, running narrative, half-time and full-time recaps | Balanced | `Narrative` |
| Personalizer | Analyst / fan / accessibility variants; EN, ES, HI, AR; favorite club or player focus | Cost | `NarrativeVariant[]` |
| Studio producer | Decides what goes on screen and when; drafts the graphic + line; submits for approval | Quality | `OverlayProposal` |

Handoffs: ingest raises a `Moment` → explainer → narrator → personalizer run as a sequential workflow
over shared `MatchState`; producer runs concurrently, consuming explainer output, and owns the proposal
queue. Failure handling: any agent timeout falls back to a templated, non-LLM line so the overlay feed
never stalls; failures are recorded in the decision log.

### 2.4 API (`services/api`)
FastAPI on Container Apps. REST for match control (start/replay/speed), proposals (approve/hold/override),
and decision log; WebSocket channels for the operator console (`/ws/operator`) and viewers
(`/ws/viewer?persona=fan&lang=es&club=...`). Publishes approved items to the `crq-overlay` Event Hub as a
timed, machine-readable overlay feed (`OverlayItem` with `t_start`, `t_end`, `layer`, `payload`).

### 2.5 Web (`web`)
React + TypeScript + Vite. Two routes: `/operator` (program feed, proposal queue with agent reasoning,
approve/hold/override, decision log, evaluation scores) and `/viewer` (synchronized overlay rendering on a
simulated pitch view, persona and language selectors, audio description toggle).

### 2.6 Evaluations (`evals`)
Foundry evaluation runs using `azure-ai-projects` 2.x: faithfulness/groundedness of each narrative against
the event window it cites, relevance, fluency per language, and content safety. Results surface in the
operator console and in a nightly GitHub Actions run.

## 3. Azure resources (sandbox)

Naming: `crq-<env>-<resource>` in resource group `rg-crq-dev`, region East US 2, tags
`project=control-room-iq`, `owner=<alias>`, `expires=2026-11-30`.

| Resource | SKU / notes | Purpose | Created by |
| --- | --- | --- | --- |
| Resource group `rg-crq-dev` | — | Container for everything | CTO office (subscription owner) |
| Microsoft Foundry resource + project `crq-dev-foundry` | Standard; Entra ID auth only | Agents, model deployments, evaluations, tracing | Agents engineer |
| Model deployment `model-router` | version 2025-11-18, Balanced; 100K TPM to start | All agent calls; underlying models chosen per call | Agents engineer |
| Model deployment `gpt-4.1-mini` | 100K TPM | Fallback and high-volume personalizer calls | Agents engineer |
| Azure AI Speech `crq-dev-speech` | S0 | Audio description (accessibility mode) | Front-end engineer |
| Event Hubs namespace `crq-dev-ehns` | Standard, 1 TU, auto-inflate to 4 | Hubs: `crq-events` (8 partitions), `crq-moments` (4), `crq-overlay` (4) | Pipeline engineer |
| Cosmos DB `crq-dev-cosmos` | NoSQL, serverless | Containers: `matches`, `state`, `moments`, `proposals`, `decisions`, `narratives` | Pipeline engineer |
| Container Apps environment `crq-dev-cae` | Consumption; Log Analytics linked | Hosts ingest, agents-runner, api, web; simulator as ACA Job | Pipeline engineer |
| Container Registry `crqdevacr` | Basic | Images built by GitHub Actions | Pipeline engineer |
| Logic App `crq-dev-approval` | Consumption | Approval SLA: auto-hold proposals with no operator action in 20 s; notifications | Front-end engineer |
| Application Insights + Log Analytics `crq-dev-appi` | — | Traces, metrics, agent spans | Pipeline engineer |
| Key Vault `crq-dev-kv` | Standard | Connection strings for local dev only; services use managed identity | Pipeline engineer |
| Storage account `crqdevst` | Standard LRS | Generated match datasets, evaluation datasets | Pipeline engineer |
| User-assigned managed identity `crq-dev-id` | — | Roles: Azure AI User, Event Hubs Data Owner, Cosmos DB Built-in Data Contributor, AcrPull | Pipeline engineer |

Quota to request on day one: model router 100K TPM in East US 2 (raise to 300K before demo day),
gpt-4.1-mini 100K TPM. Confirm Foundry Agent Service and evaluations are available in East US 2.

Estimated cost for the week at demo volumes: well under $300 (serverless Cosmos, 1 TU Event Hubs,
consumption Container Apps, a few million model tokens).

## 4. Data contracts (summary; full Pydantic models in `packages/schemas`)

- `MatchEvent`: `event_id`, `match_id`, `seq`, `t_ms` (match clock), `period`, `type`
  (`pass|carry|shot|tackle|interception|foul|clearance|possession_change|pressure|substitution|card|
  kickoff|half_end|match_end`), `team`, `player`, `x`,`y` (0–100 pitch coords), `end_x`,`end_y`, `outcome`,
  and type-specific `attrs` (pass length/angle/difficulty, shot xG/speed, pressure intensity).
- `MatchState`: score, clock, possession, per-team and per-player stats, momentum series, pressure windows.
- `Moment`: `moment_id`, `t_ms`, `kind`, `importance` (0–1), `event_ids[]`, `state_snapshot_ref`.
- `OverlayProposal` / `OverlayItem`: `layer` (`lower_third|stat_panel|heatmap|ticker|full_screen`),
  `t_start`,`t_end` (match clock), `payload`, `line` (on-air text), `reasoning`, `evaluation` (faithfulness
  score), `status` (`proposed|approved|held|overridden|aired`), `decided_by`, `decided_at`.
- `NarrativeVariant`: `persona` (`analyst|fan|accessibility`), `lang` (`en|es|hi|ar`), `text`, `audio_url?`,
  `cites[]` (event IDs).

## 5. Security and operations

Managed identity everywhere; no keys in code or images. Content safety on all generated text. Decision log
is append-only. OpenTelemetry via Agent Framework's built-in instrumentation. Health endpoints on every
service; KEDA scaling on Event Hubs lag; Bicep is the only path to create resources (no portal drift after
day one). Repository is clean-room: new code only, no proprietary code or data.

## 6. Decisions

See `docs/adr/`. ADR-001 Python + Agent Framework; ADR-002 own simulator plus LLM squad authoring;
ADR-003 model router over fixed deployments; ADR-004 Container Apps over AKS for the build week.
