# Project page — Control Room IQ

Submission draft for the Microsoft × Premier League *Inside the Game* hackathon. Keep this file in sync
with the live project page on the submission form.

---

## What it is

Control Room IQ is the AI member of the production gallery. It watches a live stream of synthetic
football events, turns them into match state, explains why a moment matters, and proposes the next
on-screen graphic with its evidence. **Nothing airs without a human.** Every proposal goes to an
operator who approves, holds, overrides or drops; there is no auto-approve setting, no autopilot timer,
and no risk threshold that lets a line air on its own. A proposal nobody acts on in 20 seconds is held,
not aired, and the hold is logged. The first viewer to receive the approved moment is the fan who
cannot hear the match: a visual cue on the strike in under a second (plain code, no model), then a
template caption on the result in under two seconds, then the operator-approved caption as soon as it
is fired, in English, Spanish or Hindi.

All match data is synthetic; clubs and players are fictional.

## The five-stage pipeline

**Ingest.** A seedable, football-realistic simulator streams passes, carries, shots (strike before
outcome), tackles, pressure, possession phases, stoppages, cards and substitutions into Azure Event
Hubs. No real match data; the simulator's hidden ground truth is what the evaluations are scored
against.

**Interpret.** An Event Hubs consumer on Azure Container Apps folds events into live state: possession,
xG, PPDA, five-minute pressure windows, momentum, speed and distance thresholds. It raises moments:
goals, big chances, momentum shifts, pressure spikes, stoppages, milestones.

**Explain.** The explainer agent says why the moment matters (control vs. chaos, pressure shift,
rhythm change) and cites the event IDs it relied on.

**Schedule and approve.** The producer agent chooses the layer, line and graphic data. A placement
scheduler assigns start and end on the match clock, checks the layer is free, takes the next clean gap
if it isn't, lets a goal or red card preempt the lower third, and advises a hold when the pressure
trend says a goal may follow. The operator console shows the proposal with its evidence, the agent's
reasoning, the model the router picked, and amber flags for any number the stats engine never produced.
Approve, hold and override are logged to an append-only decision log persisted to Azure Cosmos DB; a
20-second in-process SLA timer holds anything untouched, never airs it. Approved items go out as a
machine-readable overlay feed any graphics engine or video wall can consume. **The approval ID travels
on every packet, so the renderer is structurally unable to display anything that has not been
approved.**

**Personalize.** The narrator writes the English on-air line; the personalizer renders it per persona
and access setting; the localizer renders Spanish and Hindi in one call. The deaf fan gets the cue,
the caption and a structured context card; half-time and full-time recaps are built by code from the
match state.

## Built on Microsoft Foundry

All **five** agents (explainer, narrator, producer, personalizer, localizer) run on Microsoft Agent
Framework. The model router is deployed as **three deployments, one per routing mode** — quality for
the explainer and producer, balanced for the narrator, cost for the personalizer and localizer —
because routing mode is a per-deployment setting. The model the router actually served is recorded on
every proposal and on every trace span, one trace per moment. Every narrative is scored against the
ground-truth event window with Foundry evaluations and the score sits next to the proposal.

**Numbers come from code; words come from the model.** A code check flags any number in the English
line that the stats engine never produced, so the operator catches it before firing. Every variant is
further checked for invented numbers, name drift, cites outside the moment, banned content (referee /
betting / injury), under-length Devanagari for Hindi, and faithfulness. Operator overrides are checked
against **Azure AI Content Safety** before they are recorded or aired, so a line that doesn't pass the
service is refused with a 424. Every agent has a 12-second timeout and a deterministic template
fallback so the feed never stalls. Every operator decision is appended to the Cosmos DB decision log;
traces land in Application Insights and Foundry tracing via OpenTelemetry.

**Open-by-design guards for the public demo.** The console carries no sign-in during judging
(synthetic data only), so the API enforces guards that would be redundant with authentication: rate
limits of 120 decisions and 20 overrides per minute, a one-at-a-time replay with a cooldown, and a
daily model-call budget (`CRQ_DAILY_AI_MOMENTS`, default 300). Past the budget, moments use the
templates and the console note says why.

## Microsoft and Azure technologies

Microsoft Foundry (Agent Framework, three model-router deployments, evaluations, OpenTelemetry
tracing), **Azure AI Content Safety** (overrides checked before they air), Azure Event Hubs, Azure
Container Apps, Azure Cosmos DB (persisting the decision log), Application Insights with an
availability test on `/healthz` from three US regions, managed identity + OIDC (no secrets in the
repo), `disableLocalAuth` on Cosmos / Event Hubs / Foundry, Bicep + Azure Developer CLI, GitHub
Actions with CodeQL + Trivy + Dependabot + every action pinned to a commit SHA, and **GitHub Copilot
code review** on pull requests (findings carried in `docs/COPILOT-REVIEW.md`). An Azure Logic App for
the SLA hold, Foundry Agent Service portal registration, KEDA scaling on Event Hubs lag, and private
endpoints on the data plane are reserved for a post-submission iteration.

## Problem it solves

A production gallery has seconds to decide what goes on screen, for a growing audience that wants the
story in its own language and at its own depth. Today that depends on a few experienced people at the
desk. Control Room IQ gives them an AI colleague that surfaces, schedules and drafts, while a human
keeps control of everything that airs — **by design, not by setting.** Built by a team at Black Box, a
company that builds and operates control rooms, and validated with a senior engineering leader at the
company:

> *"When a goal is scored there's a ton of things you want to do — replay, stats, a line on screen —
> orchestrated for you in seconds. The kind of thing worth taking further."*
> — **John Hickey, Senior Director, R&D and KVM Systems, Black Box Corporation (Limerick)**

The architecture generalises to any control room that must turn a live event stream into explainable,
auditable decisions.

## Categories

**Best Enterprise Solution** (primary); also fits **Best Use of Microsoft Foundry Project** and
**Best Azure Cloud Native Integration**.

---

## What changed from the previous draft (for the author's reference)

- **Four agents → five.** Added localizer; corrected count throughout.
- **Logic App for SLA → in-process timer.** The Logic App is listed in the deferred bucket, consistent
  with the rest of the repo.
- **Content Safety.** PR #106 wired Azure AI Content Safety into the override path
  (`services/api/api/content_safety.py`); claim upgraded from "deferred" to a working control.
- **Scheduler.** PR #106 added `services/api/api/scheduler.py`. Claim upgraded from "landing shortly"
  to a working stage of the pipeline.
- **Open-demo guards.** PR #106 added rate limits, replay cooldown, daily model budget. Named as a
  working control.
- **Model router.** Corrected "a single deployment with a routing mode per agent" to "three
  deployments, one per routing mode" (which is the Foundry truth; mode is a deployment setting).
- **KEDA.** Removed from the Container Apps row; listed in the deferred bucket.
- **Foundry Agent Service portal registration.** Removed as a current claim; listed deferred
  (`register_agents.py` not in the repo).
- **Operator quote.** Replaced the fabricated placeholder with John Hickey's cleared quote.
- **GitHub Copilot agent mode → GitHub Copilot code review.** Used accurately (see
  `docs/COPILOT-REVIEW.md` and the "Fix the review of #N" commits).
- **Deaf-fan latency.** Split the strike-cue (≤ 1 s, code) from the template caption (≤ 2 s on the
  result) from the operator-approved caption; the old wording merged them.
