# Build week plan (October 20–27, 2026)

Submission deadline: October 27, 11:59 pm Pacific. Non-negotiable milestone: a working end-to-end demo
on Friday, October 23. Everything after Friday is quality, not scope.

## Roles

| Role | Owns | Day-one deliverable |
| --- | --- | --- |
| Lead (AI CoE) | Architecture, Foundry evaluations + tracing, pitch, video | Scope sign-off, repo, evaluation plan |
| Pipeline engineer | Simulator hardening, ingest/stats, Event Hubs, Cosmos, Bicep/azd, CI | `azd up` succeeds; simulator streams to Event Hubs |
| Agents engineer | Agent Framework agents, prompts, model router, squad authoring | Explainer + narrator live on Foundry against replayed moments |
| Front-end engineer | Operator console, viewer, overlay rendering, Logic Apps approval, Speech | Console shows live proposals from local replay |

## Day by day

| Day | Goal | Done when |
| --- | --- | --- |
| Tue Oct 20 | Scope, repo, sandbox request, local pipeline runs offline | `pytest` green; console shows fallback proposals from a replay |
| Wed Oct 21 | Azure foundation | `azd up` green; events flow sim → Event Hubs → ingest → Cosmos; explainer on Foundry |
| Thu Oct 22 | All four agents on Foundry; approval loop end to end; viewer personas + 4 languages | Operator approves a proposal and the viewer sees it in ES |
| Fri Oct 23 | **End-to-end demo** on the public URL; faithfulness evaluation running | 10-minute internal demo with TPS reviewer; evaluation scores on console |
| Sat Oct 24 | Hardening: failure recovery demo, SLA auto-hold via Logic Apps, Speech audio description | Kill an agent mid-match; feed keeps running and the log shows it |
| Sun Oct 25 | Polish: overlay graphics, heatmap layer, squad-authoring agent, README/ARCHITECTURE final | Someone outside the team can run it from the README |
| Mon Oct 26 | Video (<2 min), pitch text, testing instructions, repo cleanup | Video uploaded; dry-run of the submission form |
| Tue Oct 27 | Submit by noon Central; buffer | Submission confirmed |

## Demo script (2 minutes)

0:00 Problem: a control room during a live match, with a human operator. 0:15 Event stream starts; stats and
momentum move. 0:30 A big chance: explainer says why it matters, producer proposes a lower third with
reasoning and a faithfulness score. 0:45 Operator approves; the overlay appears on the viewer in English,
then Spanish, Hindi, Arabic; analyst and audio-description modes. 1:10 An agent is killed; the fallback
line airs; the decision log shows the failure. 1:25 Goal: full-screen proposal, operator overrides the
line. 1:40 Architecture slide: Foundry agents, model router, evaluations, Event Hubs, Container Apps.
1:55 Close.

## Out of scope for the week

Video auto-eventing from a feed, real hardware integration, multi-match concurrency, authentication on
the console (judges get a demo URL; the console is read-mostly and the match is synthetic).
