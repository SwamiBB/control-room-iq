 Competitive landscape and what we change — Inside the Game hackathon
 
Consolidated October 22, 2026 (evening). One document, three sources merged: the seven-repo manual read (midday), the 42-repo rubric scan (`competitive-scan-2026-10-22.md`, kept as the evidence appendix with `rubric.csv`), and the gallery pages Swami pasted (MatchLens, Director's Cut, ROAR, GroundTruth, Ninety Labs, Matchday Companion, The Gallery, MatchDesk, PitchPulse, Check Complete, Vantage, Rabona, MatchVoice).
 
## 1. The field in one paragraph
 
About 552 registered projects, roughly a third placeholders. Of 42 scanned repos, 41 are real entries and 26 are "real builds" (hosted demo, or tests + CI, and not design-only). The field has converged on one design: numbers from code, words from a model, a verifier that checks every claim against events, a producer approve/reject step, template fallback when the model fails, an agent trace, timed overlay packets, persona modes, two or more languages, evidence IDs per sentence. Several solo developers using AI coding assistants have shipped that design with tests, hosted demos and published metrics. Ten entries are rated high threat. Anything on that list is table stakes: must be present, cannot be our headline.
 
## 2. Table stakes vs. differentiators (share of the 26 real builds; ≥ 40 % = table stakes)
 
| Capability | Count | Share | Status for us |
| --- | --- | --- | --- |
| Persona / viewer modes or favorite club-player | 24 | 92 % | table stakes |
| Verifier (agent or code-only) | 23 | 88 % | table stakes |
| Two or more languages | 21 | 80 % | table stakes |
| Timed overlay packets (start + duration on match clock) | 18 | 69 % | table stakes |
| Agent Framework used | 17 | 65 % | table stakes |
| Tracing to App Insights / Foundry | 15 | 57 % | table stakes |
| Hosted demo URL | 15 | 57 % | table stakes |
| Evidence IDs per claim / fact ledger | 13 | 50 % | table stakes |
| Template fallback on model failure | most mature entries | — | table stakes |
| Bicep or azd IaC | 10 | 38 % | expected |
| Screen scheduling / layers (any) | 8 | 30 % | **contested** by the strongest entries |
| Foundry evals with published numbers | 4 | 15 % | contested by the leaders; required for credibility |
| Agent Service registration or hosted agent | 4 | 15 % | contested; cheap to add |
| Human approval loop (approve/reject or richer) | 3 (+2 unhosted) | 11 % | contested, but **everyone's is optional or editorial** |
| Live accessibility of any kind | 3 | 11 % | only blind, or replay |
| Scheduling **with** mandatory approval **with** predictive hold + SLA auto-hold | 0 | 0 % | **open** |
| Live rendering for deaf viewers tied to the approved feed | 0 | 0 % | **open** |
| Model router with per-agent routing modes, routed model in traces | 0 | 0 % | **open** |
| A real control-room operator validating the workflow | 0 | 0 % | **open; only we can do it** |
 
## 3. Entries that matter (ranked by threat to our positioning)
 
| # | Entry | What it is | Maturity | Human gate | Scheduling | Accessibility | Foundry depth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | **PitchPulse – AI Broadcast Director** (team of 3; gallery item 309) | Our concept, built: calibrated simulator, Statistician in code (xG, speed thresholds, control-vs-chaos), Analyst/Narrator/Director/Fact-Checker, TV screen, timed JSON, 7 languages + Speech, player cam, "Ask the match" via Foundry hosted MCP tool | **Live URL, video, repo**, 15 tests, OIDC, managed identity, App Insights, budgets | Optional "Producer" tick box | Duration per graphic only | None | gpt-4.1-mini fixed; hosted MCP; no evals, no router |
| 2 | **Studio Desk** (Guepe99; solo; not found in gallery by that name) | Production desk, EN/IT/ES, MCP-only data route, fact ledger, OGraf graphics, 3D pitch | 255 commits, **evals published** (groundedness 4.64/5 over 249), Content Safety, Speech, ACA + MI + Bicep | Put on air / Edit / Reject / Undo; **risk-threshold auto-approve** | Slot allocation per audience, no-overlap, max 2 cues, hold-on-desk queue, "On air now" take-out, 60 s look-ahead | None | FoundryEvals; fixed gpt-5-mini |
| 3 | **GroundTruth** (hadigghazi; item 193) | Commentary with a producer "screen budget" | Hosted, OIDC, 7 workflows | **None** | Per-layer capacity, priority preemption, wait-then-drop at `max_wait_ms`, repeat suppression, `Cue.replaces` template→verified upgrade | Code-written captions per language (not deaf-specific); Speech | Agent Framework |
| 4 | **The Gallery** (lk-nyoka; solo; item 274) | Verification-first newsroom; OBS/vMix/Vizrt feeds; house rules; readiness score; decision log; PT-BR, isiZulu | 72 tests, live demo, benchmark (0/374 unsupported passed, 37/37 planted caught); page adds PostgreSQL, Fabric, AI Search, Static Web Apps | Approve / edit (re-verified) / reject; blocked text cannot be approved | None stated | None | Foundry Local + Agent Framework workflows |
| 5 | **The Ninety Labs / Spotter** (team of 5; item 200) | Synthetic broadcast **video** → vision auto-eventing graded vs hidden answer key → data agent → Analyst/Tactician/Verifier → Producer decides → graphics on footage; **audio description for blind fans** (≤ 2 s/line, WebVTT) | ~1,900 tests, Agent Service registration, Content Safety + Prompt Shields; viewer not deployed, detection not built | Producer decides | — | Blind, not deaf | Versioned agents in Agent Service |
| 6 | **Beyond the Scoreline** (mateotoniolo) | Foundry-target entry with scheduling | Hosted | None | No overlap per layer; waits if running cue has ≤ 10 s left, else cuts short; goal/red card preempt lower third | None | Declared Best Use of Foundry |
| 7 | **rejcom Insights** | Foundry-target entry | Hosted, video, **evals 59/60**, tracing | None | Per-(profile, slot) interval booking, earliest free gap, stale low-priority drop, per-slot caps | None | Evals + tracing |
| 8 | **MatchMind** (kaanoguzkan) | Deepest Foundry surface in the field | Hosted, **evals 30/30 groundedness**, **8 registered prompt agents + hosted agent** | None | One lower-third at a time per cohort; late items dropped or demoted to ticker; 20 s fast-path deadline | Screen-reader live region, reduced motion, high contrast (UI hygiene) | Agent Service, evals |
| 9 | **Matchday Companion** (ogu83; item 5) | "Co-commentator you can interrupt, and that can't lie" | Hosted agent via azd, video, **evals: planted errors 0/4 vs 4/4, groundedness 4.75 vs 3.83** | None | — | None | Declared Best Use of Foundry |
| 10 | **Matchroom**, **The Dugout**, **Playmakers** | Matchroom: 3 versioned Agent Service agents + numbers. Dugout: overall maturity, ~4 s hold per cue. Playmakers: Compliance gate, **kill-and-recover from checkpoint**, azd + Bicep, live eastus2 | High | None | Minor | None | Agent Service (Matchroom) |
| 11 | **ROAR** (solo student; item 347) | Deaf-fan experience: 3 registers × 4 languages, haptics with on-screen stand-in, Three.js stadium, VAR-aware verification | 9 commits, 17 tests, **no hosted demo**, replay of 18 moments | None | — | **Deaf**, replay only | **None implemented**; deterministic "agents" |
| 12 | **MatchLens by Dhisana** (company) | Correction propagation when VAR voids a goal; EN/ES; honest 8-case eval (8/8 vs 3/8) | Live, video, repo | None | None | None | OpenAI Agents SDK, not Agent Framework |
| 13 | **Pitchside** (csaras84), **Audio Eyes**, **MatchGist**, **Deepkick** | Deaf/blind/deafblind recap; blind spatial audio; SMS/watch-glance; per-minute overlay cap | Early | None | Deepkick: 3/min cap | Recap-only or not deaf | Thin |
| — | **Check Complete** (item 201: AKS, Private Endpoints, APIM, Fabric RTI, producer approves; no repo), **MatchDesk** (item 284: near twin of our design, plan only), **Director's Cut** (AI-written concept, no repo), **Producer Co-pilot** (diwahsap; approve/edit/reject, unhosted), **Premier-League-Challenge** (officiating; Gemini), **anontrenchpaper** (research pack recommending almost our concept; catalogs 10+ competitor repos in `research/06`), **MatchVoice AI** ("signing commentary" tag is a misnomer) | Placeholders, plans or non-threats | — | — | — | — | — |
 
## 4. Lane status
 
**Lane 1, operator screen scheduling: contested.** Seven entries schedule layers; four with collision, preemption or hold/drop logic (Studio Desk, GroundTruth, Beyond the Scoreline, rejcom, plus MatchMind's cohort rule). What none has: scheduling **combined with** a mandatory operator approval loop **and** predictive hold advice ("a goal may follow; hold the xG card"). Studio Desk has approval + slots, but its hold is a queue, not advice, and it auto-approves low-risk items. Nobody has an SLA auto-hold or a real control-room operator quoted.
 
**Lane 2, live accessibility tied to production: open.** Zero entries render for deaf viewers during play. Nearest: The Ninety Labs (blind, audio description, not deployed), GroundTruth (generic live captions), Pitchside (deaf profile, recap only), ROAR (deaf, replay only, no Microsoft stack). No entry delivers an operator-approved moment to a deaf viewer during play with a strike → result cue pair.
 
**Lane 3, Foundry depth: contested on evals and Agent Service, open on model router.** Four publish evaluator numbers (Studio Desk, rejcom, MatchMind, Matchday Companion); four register or host agents (MatchMind, Matchroom, Ninety Labs, Matchday Companion); Content Safety in two; Foundry Local in two. None uses the model-router deployment with per-agent routing modes, and none states the chosen model in trace spans.
 
## 5. Category contenders
 
- **Best Use of Microsoft Foundry:** Matchday Companion (declared), MatchMind, Beyond the Scoreline (declared), Matchroom, rejcom, PitchPulse (hosted MCP tool, Agent Framework).
- **Best Enterprise Solution:** Studio Desk (declared; approval + slots + evals + Content Safety + MI), Playmakers, GroundTruth, MatchMind, The Ninety Labs, Check Complete (if it ships).
- **Best Multi-Agent:** Playmakers (declared), MatchLens (declared), MatchMind, Ninety Labs.
- **Grand Prize shape:** The Ninety Labs (auto-eventing from video, the one prong nobody else attempts), Studio Desk, PitchPulse, The Gallery.
## 6. What we change in the project
 
### 6.1 Positioning (pitch, tagline, first 20 seconds of the video)
 
Lead with the gallery, not the newsroom: *"Control Room IQ is the AI member of the production gallery. It schedules the screen, and nothing airs without a human, by design, not by setting. The first viewer to get the approved moment is the fan who can't hear it."* Then the Foundry line: Agent Framework agents, model router choosing the model per call, every narrative scored by Foundry evaluations, every decision logged. Make "deaf fan, during play, operator-approved" explicit in the first 20 seconds so judges do not file us next to The Ninety Labs (blind, replay) or ROAR (deaf, replay).
 
Proposed tagline (replaces the current one, which leads with "four languages"): *"The AI member of the production gallery: Foundry agents schedule the screen, a human approves every graphic, and the approved moment reaches deaf fans live, in their language."*
 
### 6.2 Add to Friday's must-haves
 
1. **Layer scheduler** in the producer path: layer choice, start/end on the match clock, no two items on one layer, next clean gap (rejcom's "earliest free gap"), "one story per window" anti-spam (Director's Cut), goal/red card preempt the lower third (Beyond the Scoreline), **hold advice** from `pressure_trend`, and the **SLA auto-hold** (20 s; Logic App in Azure, timer locally). The combination is the only production-side feature nobody has; scheduling alone reads as parity with Studio Desk and GroundTruth.
2. **Mandatory operator gate**: no auto-approve path (unlike Studio Desk's risk threshold and PitchPulse's tick box); air only by approve or override; every action logged including SLA holds. Say so in the pitch.
3. **Deaf-fan live beat**: `shot_taken` → cue within ~1 s (team, direction, crowd level, on-screen pulse as the haptic stand-in borrowed from ROAR) → `shot` → caption within ~2 s with plain-language chance quality and past/now/next context; delivered only after the operator's decision on the matching proposal (`FanCard` as designed in the data model).
4. **Model router** as the only deployment the agents call; routing mode per agent (explainer/producer Quality, narrator Balanced, personalizer Cost); **routed model recorded on every span** and shown in the console's reasoning panel. README leads the Foundry section with it: no one else has it.
5. **Foundry evaluation table in the README** by Monday: faithfulness/groundedness, relevance, fluency per language on the reference match, plus a planted-falsehood check (N injected, N caught), the format Studio Desk, rejcom, MatchMind and Matchroom use. Honest framing as MatchLens does ("diagnostic, not proof").
6. **Agent Service registration** of the four agents (cheap; four entries have it; makes them inspectable in the Foundry portal).
7. **Operator validation**: 30 minutes with a real Black Box control-room operator Thursday or Friday; one quoted sentence in README and video. Nobody else can get this.
### 6.3 Cut or demote
 
- Languages: **three** (EN, ES, HI), not four; Arabic/RTL dropped unless free (80 % of real builds have 2+ languages).
- Blind-fan audio description via Speech: drop (Ninety Labs owns it; our accessibility persona is deaf).
- Analyst persona as a designed experience: keep only as a switch (92 % have persona modes).
- Kill-an-agent scene: 10-second beat, not a hero scene (Playmakers owns it with checkpoint replay).
- Squad-authoring agent, heat-map layer, what-if, player cam, voice: only if nothing else is left on Sunday.
- "Verified before air", "MCP server", "evidence IDs": mention once as table stakes, never as headlines (88 %, 5+ entries, 50 %).
- "Goal corrected" VAR beat (MatchLens, ROAR): parked for Sunday if the core demo is done.
### 6.4 Category
 
Declare **Best Enterprise Solution** as primary and Best Use of Microsoft Foundry as secondary. Our only unique features (mandatory gate, scheduling with SLA, audit log, operator validation, managed identity, Bicep) are the Enterprise rubric word for word; the Foundry box has five entries with hosted agents and published evals telling the "Foundry made us faster" story better than a mandatory-gate product can. Studio Desk is the Enterprise incumbent but auto-approves and is solo; Check Complete has the enterprise stack but no repo yet. The learning goal (Foundry depth) is unchanged; the label only changes who we are compared with, and judges may reassign anyway.
 
### 6.5 README and project page format (copy the leaders)
 
Top of README: live demo URL, 2-minute video, evaluation table, planted-falsehood result, test count, one line on what is synthetic. Then a judge walkthrough with exact clicks and no login (MatchLens, PitchPulse format), an honest limits section, a disclosed defect and fix. Post a progress comment on our gallery page when the URL is live (ours shows 0 comments; leaders show 3–6).
 
### 6.6 Monday deliverable checklist (against the leaders)
 
Hosted public URL with a pre-loaded replay · video < 2 min with the new first 20 seconds · README per 6.5 · Foundry eval table · ≥ 20 tests green in CI · Bicep/azd one-command deploy · decision log download · operator quote · tagline and category updated on the project page.
 
## 7. Decisions needed from Swami (the scan's six questions, with recommendations)
 
1. **Lane 1 differentiator.** Recommend: yes, "scheduling with mandatory approval with predictive hold advice + SLA". If `hold_advice` cannot ship Friday, ship the scheduler + SLA Friday and hold advice Saturday; without it, scheduling reads as parity.
2. **Lane 2 in the video.** Recommend: yes, "deaf fan, during play, operator-approved" in the first 20 seconds (6.1).
3. **Model router.** Recommend: yes for Friday, and lead the README's Foundry section with it (6.2 item 4).
4. **Category.** Recommend: Best Enterprise primary, Foundry secondary (6.4). Confirm.
5. **Published eval table.** Recommend: commit to it as a Monday deliverable (6.2 item 5).
6. **Next scan.** Recommend: add the anontrenchpaper `research/06` repo list to `seed.json`; re-run Sunday to catch Check Complete, MatchDesk, Director's Cut and GroundTruth's final pages.
Plus two from the page reads: confirm EN/ES/HI as the three languages, and name the control-room operator and the day.