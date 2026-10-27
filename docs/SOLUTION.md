# Control Room IQ — Solution Description

Version 0.1 · October 20, 2026 · Inside the Game: Developer Hackathon (Microsoft × Premier League)

## 1. One paragraph

Control Room IQ is an AI operator for the live production control room. It ingests a stream of synthetic
football events, turns them into live match state, explains why each key moment matters, proposes what
should go on screen and when, and routes every proposal through a human operator before it reaches the
overlay feed. The same intelligence is personalized for an analyst, a casual fan, and an audio-description
accessibility mode in English, Spanish, Hindi, and Arabic. It is built on Microsoft Foundry (Agent
Framework agents, model router, evaluations, tracing) and runs on Azure cloud-native services (Event
Hubs, Container Apps, Cosmos DB), deployed with one `azd up`.

## 2. The problem

A live football production has seconds to decide what goes on screen. Statistics arrive faster than a
gallery can read them, the story of the match (pressure building, momentum turning, a player quietly
dominating) is visible only to the most experienced people in the room, and every graphic that airs is
seen once by everyone, in one language, at one depth. Streaming has multiplied the audiences but not the
people producing for them.

Three jobs are done badly today:

| Job | Today | Gap |
| --- | --- | --- |
| Spot what matters, now | Experienced producers scanning a stats feed and the pictures | Pressure shifts, rhythm changes, and milestones are missed or noticed late |
| Explain it on air | Presenter improvises from memory | Numbers get misquoted; the "why" is rarely tied to evidence |
| Reach every viewer | One graphic, one language, one depth | The analyst, the first-time fan, and the viewer who cannot see the picture all get the same thing |

The constraint that makes this hard is trust: nothing can go on air that is wrong, and a human must stay
accountable for every graphic. Fully automated generation is not an option for a broadcaster; neither is
an assistant that is too slow or too vague to use during live play.

## 3. The solution

Control Room IQ answers all three jobs with one pipeline and one principle: the AI proposes, explains,
and personalizes; the operator decides.

**Ingest and interpret.** A football-realistic synthetic event stream (passes, carries, shots with xG and
speed, tackles, pressure events, possession changes, cards, substitutions) is folded in real time into
match state: possession, pass completion, expected goals, PPDA, momentum, pressure windows, and per-player
distance and top speed with threshold triggers. The state engine raises *moments* with an importance score
and the event IDs behind them. This layer is deterministic and is the ground truth everything else is
judged against.

**Explain.** A tactical explainer agent receives each moment with the full state snapshot and says why it
matters, choosing one dominant pattern (control, chaos, pressure shift, rhythm change, individual, set
piece), and cites the events it relied on. It may use only facts in its input.

**Render.** A studio producer agent decides whether the moment deserves a graphic, which layer (lower
third, stat panel, heat map, ticker, full screen), the timing on the match clock, the on-air line, and the
exact numbers the renderer needs, and it explains its decision in two sentences including the alternative
it rejected. The proposal lands in the operator console with a faithfulness score. The operator approves,
holds, or overrides; the API auto-holds anything untouched for 20 seconds. Approved items are
published as a timed, machine-readable overlay feed a graphics engine, video wall, or streaming client can
consume.

**Personalize.** Narrator and personalizer agents turn the approved line into variants: analyst (one
supporting statistic added), fan (warmer, club- or player-focused), and accessibility (a self-contained
audio description, voiced with Azure AI Speech), each natively written in EN, ES, HI, and AR. Viewers
pick persona, language, and favorite club or player; the same moment reaches each of them differently.

**Trust.** Every narrative is scored for faithfulness against the cited events and state snapshot using
Foundry evaluations; every agent call has a timeout and a deterministic fallback so the feed never
stalls; every decision, including automated holds and fallbacks, is written to an append-only log. All
agent spans are traced to Application Insights, including which model the router selected per call.

## 4. Who it is for

| User | What they get | Where they see it |
| --- | --- | --- |
| Gallery producer / director | A ranked queue of "next on screen" proposals with reasoning and evidence; one-click control | Operator console |
| Presenter / commentator | An on-air line that is tied to the data and safe to read | Operator console (talent view, roadmap) |
| Graphics operator / rendering partner | A timed, structured feed with layer, start/end, and payload | Overlay feed (WebSocket + Event Hub) |
| Analyst viewer | Depth: the statistic behind every line, momentum and pressure context | Viewer, analyst persona |
| Casual fan | A warm, simple story, in their language, about their club or player | Viewer, fan persona |
| Viewer who cannot see the picture | A self-contained audio description of each moment | Viewer, accessibility persona |
| Streaming platform / studio | A drop-in intelligence layer with evaluation and audit built in | API + feed |

## 5. Scenarios the demo shows

1. **A big chance, explained and proposed.** Minute 57, a shot saved with xG 0.38. The explainer calls it
   "chaos": the away side's pressure count doubled in the last five minutes and possession flipped. The
   producer proposes a lower third with the xG and pressure numbers. Faithfulness 0.94.
2. **The operator overrides.** The operator rewrites the line, approves; the viewer sees the override in
   Spanish, then Hindi, then Arabic, as analyst depth and as audio description.
3. **An agent fails.** The agents service is killed mid-match. The next moment airs from the template
   fallback, the console flags it, and the decision log records the failure. The feed never stops.
4. **A goal.** Full-screen proposal with the match story so far; approved; half-time recap written from
   the state snapshot with minutes and the standout player.

## 6. Why Microsoft Foundry is the center of the design

| Need | Foundry capability | How it shows in the project |
| --- | --- | --- |
| Four specialized agents with shared state and handoffs | Agent Framework (agents, sequential + concurrent workflow), Foundry Agent Service | `services/agents/workflow.py`; explainer → narrator sequential, personalizer ∥ producer concurrent |
| The right model per job, at the right cost and latency | Model router (one deployment, Balanced/Quality/Cost routing, model recorded per call) | Explainer and producer on Quality, personalizer on Cost; routed model visible in traces |
| Proof that narratives are true to the data | Foundry evaluations (groundedness/faithfulness, relevance, fluency, safety) | Score per proposal in the console; nightly evaluation run in CI |
| See every decision end to end | Tracing via OpenTelemetry to Application Insights | Spans per agent call, per moment, per decision |
| Safe output in four languages | Foundry's default content filters on every model deployment | Applied to every model call; a dedicated Content Safety resource is deferred |
| Faster development | GitHub Copilot agent mode; declarative agents and prompts in the repo | Prompts as versioned Markdown; agents built in a week by four people |

## 7. Fit to the hackathon

**Challenge requirements.** The five-stage pipeline (ingest, interpret, explain, render, personalize) is
the structure of the system. Real-time match intelligence: player tagging with speed and distance
thresholds, pass distance, difficulty and accuracy, ball and shot speed. Narrative generation: lines,
running narrative, half-time and full-time recaps. Explainability: control vs. chaos, pressure changes,
rhythm. Data innovation: a seedable match engine and an LLM squad-authoring agent that extend the
synthetic dataset. Multi-language storytelling: EN/ES/HI/AR written natively, not translated.

**Categories.** Primary: Best Use of Microsoft Foundry. Also fits Best Azure Cloud Native Integration
(event-driven pipeline on Event Hubs, Container Apps, Cosmos DB, azd) and Best
Enterprise Solution (human-in-the-loop, evaluation, audit log, managed identity only, infrastructure as
code).

**Judging criteria.**

| Criterion | Where to look |
| --- | --- |
| Technological implementation | Synthetic data engine with tests; typed contracts in `packages/schemas`; Bicep for every resource; CI; hero technologies throughout |
| Agentic design and innovation | Four agents with distinct roles, shared state, concurrent + sequential orchestration, timeouts and fallbacks, decision log; producer agent that reasons about screen real estate and timing |
| Real-world impact | Built for an existing job in every live production; output is a feed a rendering partner can consume today |
| User experience and presentation | Operator console and viewer are two deliberately different experiences; two-minute video follows the demo script in `PLAN.md` |
| Adherence to category | Foundry is the reasoning, routing, evaluation, and observability layer, not a wrapper |

## 8. What is synthetic and what is not

All match data is generated by the simulator in this repository from fictional clubs, players, and
venues; no real competition data is used or redistributed. Fictional storylines produced by the squad
authoring agent are labeled as fiction in the narrator's context. The system's architecture, contracts,
and agents are the real deliverable.

## 9. After the hackathon

Auto-eventing from a video feed (replacing the simulator with a vision model), a talent view for
presenters, operator profiles and permissions, multi-match concurrency, and a rendering-partner adapter
for a specific graphics engine. The event and overlay contracts are designed so that only the ingest edge
and the render edge change.
