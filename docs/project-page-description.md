# Project page description — draft of Oct 22, 2026 (evening)
 
Replaces the Oct 20 description. Square brackets are figures that do not exist until the weekend; omit rather than guess if not ready by Monday noon. Keep the Agent Service and routing-mode sentences only if they ship.
 
## What it is
 
Control Room IQ is the AI member of the production gallery. It watches a live stream of synthetic football events, turns them into match state, explains why a moment matters, and schedules the screen: which graphic, on which layer, from when to when, with no collisions, and a hold when the pressure trend says a goal may follow. Nothing airs without a human. Every proposal goes to an operator who approves, holds, or overrides it; there is no auto-approve setting, and a proposal nobody acts on within 20 seconds is held automatically and logged. The first viewer to receive the approved moment is the fan who cannot hear the match: a visual cue on the strike, a plain-language caption on the result, within about two seconds, in English, Spanish, or Hindi.
 
Live demo: [URL, pre-loaded replay, no login]. Video: [link]. [N] tests in CI. Foundry evaluation: [faithfulness x.xx / relevance x.xx / fluency x.xx over N narratives in 3 languages; N planted falsehoods, N caught]. All match data is synthetic; clubs and players are fictional.
 
## The five-stage pipeline
 
1. Ingest. A seedable, football-realistic simulator streams passes, carries, shots (including the strike before its outcome), tackles, pressure events, possession phases, stoppages, cards, and substitutions into Azure Event Hubs. No real match data is used; the simulator's hidden ground truth is what the evaluations are scored against.
2. Interpret. An Event Hubs consumer on Azure Container Apps folds events into live state: possession, xG, PPDA, five-minute pressure windows, momentum, speed and distance thresholds. It raises moments: goals, big chances, momentum shifts, pressure spikes, stoppages, milestones.
3. Explain. A tactical explainer agent says why the moment matters (control vs. chaos, pressure shift, rhythm change) and cites the event IDs it relied on.
4. Schedule and approve. A producer agent chooses the layer, start and end on the match clock, the line, and the graphic data, checks the layer is free, takes the next clean gap if it isn't, lets a goal or red card preempt the lower third, and advises a hold when a goal may follow. The operator console shows the proposal with its evidence and the agent's reasoning. Approve, hold, and override are logged; an Azure Logic App enforces the 20-second SLA. Approved items go out as a timed, machine-readable overlay feed that any graphics engine or video wall can consume, and the approval ID travels on every packet, so the renderer is structurally unable to display anything that has not been approved.
5. Personalize. Narrator and personalizer agents render the approved moment for the deaf fan (cue, caption, past/now/next context), for a casual fan, and for an analyst, in EN/ES/HI, plus half-time and full-time recaps.
## Built on Microsoft Foundry
 
All four agents run on Microsoft Agent Framework and are registered in Foundry Agent Service, so each is inspectable and versioned in the Foundry portal. They call a single model-router deployment with a routing mode per agent (quality for the explainer and producer, balanced for the narrator, cost for the personalizer); the model the router chose is recorded on every trace span and shown to the operator in the reasoning panel. Every narrative is scored for faithfulness against the ground-truth event window with Foundry evaluations, and the score sits next to the proposal. Numbers come from code, words from the model, and a verifier checks every claim before it can be proposed. Every agent has a timeout and a deterministic fallback so the feed never stalls; failures and every operator decision go to an append-only decision log the judges can download. Spans are traced with OpenTelemetry to Application Insights and Foundry tracing.
 
## Microsoft and Azure technologies
 
Microsoft Foundry (Agent Framework, Foundry Agent Service, model router, evaluations, tracing, Content Safety), Azure Event Hubs, Azure Container Apps (KEDA scaling on event lag), Azure Cosmos DB, Azure Logic Apps, Application Insights, managed identity, Bicep + Azure Developer CLI, GitHub Actions, GitHub Copilot agent mode. (Add Azure AI Speech back only if the deaf-fan cue uses it.)
 
## Problem it solves
 
A production gallery has seconds to decide what goes on screen, and a growing audience that wants the story in its own language and at its own depth. Today that depends on a few experienced people at the desk. Control Room IQ gives them an AI colleague that surfaces, schedules, and drafts, while a human keeps control of everything that airs, by design, not by setting. It was built by a team at Black Box, a company that builds and operates control rooms, and validated with a working control-room operator: "[operator quote]". The architecture generalizes to any control room that must turn a live event stream into explainable, auditable decisions.
 
## Categories
 
Best Enterprise Solution (primary); also fits Best Use of Microsoft Foundry and Best Azure Cloud Native Integration.
 
## Tagline (separate field)
 
The AI member of the production gallery: Foundry agents schedule the screen, a human approves every graphic, and the approved moment reaches deaf fans live, in their language.
 
Short form if length-limited: Foundry agents schedule the screen; a human approves every graphic; deaf fans get the approved moment live.
 
## Why these changes (vs. Oct 20 copy)
 
- Opening carries the three unique claims (mandatory gate, scheduler with hold + SLA, deaf fan live) instead of the generic five-stage pipeline.
- Arabic, audio-description mode, squad-authoring agent removed (cut Oct 22); analyst demoted to a switch.
- Stage 4 renamed "Schedule and approve"; approval ID on the packet stated as a structural guarantee (Studio Desk's approvals are per-visitor).
- Foundry section leads with model router + Agent Service (none of the Foundry-category leaders have router); verifier/evidence IDs demoted to one sentence (88 % / 50 % of the field).
- Proof block at the top in the leaders' format (URL, video, tests, eval table, planted falsehoods, synthetic note).
- Category order swapped to Best Enterprise primary.