# Landscape — Inside the Game hackathon — scan of 2026-10-22 (first run)
 
Method: 42 public repos found by web search (GitHub search API unavailable from the sandbox), shallow-cloned and read against the fixed rubric in `templates/rubric.md` by five parallel readers. Facts only; see `rubric.csv` for per-repo evidence. Commit counts are not available from shallow clones; last-commit dates are real. Baseline for the diff is the seven-repo manual read in the project doc (`competitive-read.md`).
 
## Headline
 
- Universe: 42 repos, 41 real hackathon entries (one is an unrelated tutoring app). 26 are "real" (hosted demo or tests + CI, and not design-only); 15 are placeholders, plans, or generator-only.
- 10 entries are rated **high** threat, up from 2 in the seven-repo read. Four of them were not in the previous read: GroundTruth, MatchMind (kaanoguzkan), Matchday Companion (ogu83), Matchroom, plus The Dugout, Beyond the Scoreline, The Ninety Labs and rejcom's Insights.
- **Lane 1 (screen scheduling) is no longer open.** Seven entries schedule layers, four of them with collision, preemption or hold/drop logic. The previous read's "no entry schedules layers" was wrong at the field's current size.
- **Lane 2 (live deaf-fan delivery) is still open.** Zero entries render for deaf viewers during play. The nearest is The Ninety Labs (audio description for blind viewers, viewer not deployed) and Pitchside (deaf profile, recap only).
- **Lane 3 (Foundry depth) is contested on evals and Agent Service, open on model router.** Four entries publish Foundry evaluator numbers; four register or host agents in Foundry Agent Service. None uses the model-router deployment with per-agent routing modes.
## Table stakes (share of the 26 real entries; ≥ 40 % = table stakes)
 
| Capability | Count | Share | Status |
| --- | --- | --- | --- |
| Persona / viewer modes or favorite club-player | 24 | 92 % | table stakes |
| Verifier (agent or code-only) | 23 | 88 % | table stakes |
| Two or more languages | 21 | 80 % | table stakes |
| Timed overlay packets (start + duration on match clock) | 18 | 69 % | table stakes |
| Agent Framework used | 17 | 65 % | table stakes |
| Tracing to App Insights / Foundry | 15 | 57 % | table stakes |
| Hosted demo URL | 15 | 57 % | table stakes |
| Evidence ids per claim / fact ledger | 13 | 50 % | table stakes |
| Bicep or azd IaC | 10 | 38 % | borderline |
| Screen scheduling / layers (any) | 8 | 30 % | differentiating, but contested by the strongest entries |
| Foundry evals with published numbers | 4 | 15 % | differentiating |
| Agent Service registration or hosted agent | 4 | 15 % | differentiating |
| Human approval loop (approve / reject or richer) | 3 | 11 % | differentiating |
| Live accessibility of any kind | 3 | 11 % | differentiating |
| Model router with per-agent routing modes | 0 | 0 % | unique if we ship it |
| Live rendering for deaf viewers | 0 | 0 % | unique if we ship it |
 
Template fallback on model failure is present in most mature entries (counted loosely; the rubric does not isolate it). Treat it as table stakes.
 
## Our three lanes
 
### Lane 1 — operator screen scheduling (layers, start/end, collisions, hold, SLA)
 
| Repo | What they have | Threat |
| --- | --- | --- |
| Guepe99/studio-desk | Slot allocation per audience, no-overlap rule, max 2 cues overlapping, hold-on-desk queue, "On air now" with take-out, 60 s look-ahead. Plus approve/edit/reject/undo and risk-threshold auto-approve. Targets Best Enterprise. | high |
| hadigghazi/groundtruth | Producer "screen budget": per-layer capacity, priority preemption, wait-then-drop at `max_wait_ms`, repeat suppression, `Cue.replaces` for template→verified upgrade. No operator approval. | high |
| mateotoniolo/beyond-the-scoreline | No two cues overlap on a layer; cue waits if the running one has ≤ 10 s left, else cuts it short; goal/red card preempt the lower third. Claims Best Use of Foundry. | high |
| rejcom/inside-the-game-insights | Per-(profile, slot) interval booking, earliest free gap, stale low-priority drop, per-slot caps in the player. Foundry evals with numbers. | high |
| kaanoguzkan/insidethegamehackathon | One lower-third at a time per cohort, late items dropped or demoted to ticker, 20 s fast-path deadline with template fallback. | high |
| lauramiro/the-dugout | Minimum ~4 s hold per cue only. | high (overall maturity, not this lane) |
| MohamedAtiyah/Deepkick | Per-minute cap of 3 overlays, priority drops. | medium |
 
What none of them has: scheduling **combined with** an operator approval loop **and** a predictive hold ("a goal may follow, hold the xG card"). Studio Desk has approval + slots but its hold is a queue, not advice. Nobody has an SLA auto-hold (Logic Apps) or a real control-room operator quoted.
 
### Lane 2 — live accessibility tied to production
 
| Repo | What they have | Gap vs our design |
| --- | --- | --- |
| KLKH7/the-ninety-labs | Audio description for blind/low-vision viewers, target ≤ 2 s per line, large on-screen caption, WebVTT. Team entry, ~1,900 tests, Agent Service registration, Content Safety. Viewer not deployed; event detection from video not built. | Blind, not deaf; no sound cues; not tied to an operator's approval |
| hadigghazi/groundtruth | Code-written play-by-play captions per language, live; Azure Speech commentary | Generic captions, no deaf-specific cues or two-beat structure |
| csaras84/pitchside | Deaf profile: captions + sound cues + vibration + flash; blind and deafblind profiles; 5 languages | Recap of a finished match only; unhosted; no Foundry depth |
| kaanoguzkan/insidethegamehackathon | Screen-reader live region, reduced motion, high contrast | UI hygiene, not a deaf-fan experience |
 
No entry delivers an operator-approved moment to a deaf viewer during play with a strike → result cue pair. This lane is open.
 
### Lane 3 — Foundry depth
 
| Feature | Entries that have it |
| --- | --- |
| Foundry evaluators with published numbers | Studio Desk (249 items, groundedness 4.64/5), rejcom (60 items, 59/60), MatchMind (30 items, 30/30 groundedness), Matchday Companion (planted errors 0/4 vs 4/4, groundedness 4.75 vs 3.83) |
| Agent Service registration / hosted agent | MatchMind (8 registered prompt agents + hosted agent), Matchroom (3 versioned agents, hash-based versioning), The Ninety Labs (versioned ninety-analyst / ninety-judge), Matchday Companion (hosted agent via azd) |
| Content Safety | Studio Desk, The Ninety Labs (with Prompt Shields) |
| Foundry Local | The Gallery (headline only), PRO-VISION adapter |
| Model router deployment with per-agent routing modes | none |
| Chosen model recorded in trace spans | none stated |
 
## Category contenders
 
Best Use of Microsoft Foundry (our primary): Matchday Companion (ogu83; declared target, hosted agent, evals, video), MatchMind (kaanoguzkan; secondary target, deepest Foundry surface), Beyond the Scoreline (declared target, hosted, scheduling), Matchroom (Agent Service + numbers), rejcom (evals + tracing + video).
 
Best Enterprise: Studio Desk (declared target, approval + slots + evals + Content Safety + managed identity), Playmakers (hosted, checkpoints, operational metrics), GroundTruth (screen budget, OIDC deploy, 7 workflows), MatchMind, The Ninety Labs.
 
## Changes since the seven-repo read
 
- New high-threat entries: GroundTruth, MatchMind, Matchday Companion, Matchroom, The Dugout, Beyond the Scoreline, The Ninety Labs, rejcom Insights.
- Lane 1 moved from "open" to "contested by five mature entries".
- Lane 3 moved from "nobody has Foundry evals except Studio Desk" to "four have evals, four have Agent Service; router still untouched".
- Truecast and LiveDesk are weaker than the previous read suggested: Truecast does not use Agent Framework; LiveDesk has only a Go simulator built.
- Two entries have approve/edit/reject loops we had not seen: diwahsap's Producer Co-pilot (unhosted) and Premier-League-Challenge (officiating; Gemini, not Foundry).
- One entry (anontrenchpaper) is a research pack whose recommended concept is almost ours (Director agent, per-viewer overlays, producer approval), design-only, and it catalogs 10+ competitor repos in its `research/06` file.