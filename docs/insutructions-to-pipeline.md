Purpose and scope
The pipeline engineer wears two hats this week: scenes & data owner (the critical path through Thursday) and platform owner (simulator, ingest, Event Hubs, Cosmos, Bicep/azd, CI). This doc is the action list for both hats, Thursday through Tuesday, with a done-criterion per item.
It sits beside three other role docs: the Scenes & Data Owner role brief (the contract for the data chain: personas, moments, questions, schema, reference match, evaluation dataset), the agent design and orchestration plan, and the front-end envelope contracts. Where the brief and this doc disagree, the brief wins, because it is what the agents and front-end engineers reviewed; this doc schedules its deliverables and adds the platform work the brief does not cover. Everything here is additive to the committed scaffold; nothing in the repo is removed.
What changed after the competitive read
The nine decisions from the October 22 landscape move six things in this plan, all of them earlier or sharper; nothing new is added to the simulator beyond the strike cue inputs.
Landscape decision
Effect on the pipeline plan
2. Build the scheduler, not another agent
Layer scheduler (no collisions, earliest free gap, one story per window, goal/red card preempt) and the 20 s SLA auto-hold move to Friday. Hold advice from pressure_trend is computed in code, Friday if possible, Saturday at the latest.
3. Mandatory gate
No auto-approve path in the API; every state change (operator, SLA, supersession) lands in a decisions log with a CSV download. Friday.
4. Deaf fan live, tied to approval
shot_taken carries direction; crowd is emitted at a steady cadence from Thursday, not Saturday, so the strike cue and crowd meter work in Friday's demo. FanCard result beat is released only after the operator decides.
5. Foundry depth
Evaluation record stores the routed model per call; Saturday's dataset includes a planted-falsehood set (injected wrong numbers and names) with expected catches.
6. Cut what the field has
Three languages (EN, ES, HI) in fixtures and replay. Squad-authoring agent intake drops to Sunday-if-empty; the hand-written storyline is the plan, not the fallback. Heat-map layer and what-if are out.
7, 8. Enterprise primary, leaders' proof format
Managed identity everywhere, no keys in config; ≥ 20 tests green in CI; decision log and audit trail named in the README's enterprise section.
9. Get the operator
The replay with jump-to-moment must be usable Thursday evening or Friday for the 30-minute operator session; their changes to layers or timings go straight into the scheduler config.
What the pipeline engineer owns
One person owns the path from synthetic event to stored state, and the infrastructure it runs on. The agents engineer owns everything that calls a model; the front-end engineer owns everything the eye sees.
Area
Owns
Hands off to
Simulator
Seeded, scripted match generator; storyline → events at known minutes; new event types; tracking-style position stream; crowd curve
Reference match file in data/
Ingest / stats engine
Event parsing, MatchState, shot ledger, xG windows, pressure_trend, momentum_label, zone namer, phase and stoppage summaries, player_focus, milestones
MatchState over WebSocket; moment snapshots
Moment detector
Rules module over MatchState: thresholds, beats, priority, snapshot per moment type
Moment records to the agent workflow
Event Hubs
Namespace, hub, consumer group; producer in the replay driver; consumer in the API
Live event stream for the hot path
Cosmos DB (serverless)
Containers for events, state checkpoints, proposals, fan cards, evaluation records; partition keys
Read models for the API; rows for Foundry evaluation
Bicep / azd
Every resource as code; azd up to a public URL; environment variables and secrets
Judges' URL; CI deploy target
CI/CD
GitHub Actions: lint, tests, container build, OIDC deploy on main
Green pipeline for the whole team
Offline mode
CRQ_OFFLINE=1 runs the full pipeline from the reference match and fixtures with no Azure
The other three never block on quota
Evaluation dataset
Reference match × moments × expected answers; evaluation record row format
Foundry evaluation run (Swami, Saturday)
Thursday, October 22: schema, simulator, reference match
Thursday is the scenes & data hat. Done means the other three can build against real files by end of day; no Azure is needed for any of it.
Morning (by 10:00)
[ ] Run the 15-minute schema review with the agents and front-end engineers. Bring the additive change list (new events, new fields, derived state, experience records) and the snapshot composition per moment type. Decide the priority table and supersession rules with the agents engineer in the same slot.
[ ] Finish stages two and three (questions, information needed) for goal and stoppage in that review; big chance is done.
[ ] Commit fixtures by mid-morning: one MatchState JSON, one Moment per demo moment type (big chance strike and result, goal, stoppage with card), one FanCard, one OverlayProposal. Fixtures are the contract until live wiring.
Simulator and stats engine (by EOD)
[ ] Event shape rule (from the brief): every raw event is a record in the Opta-style event model: type, qualifier list, team and player ids, period / minute / second, x and y on a 0–100 grid with attacking direction normalized, outcome flag. Our additions are event types and qualifiers in that shape, not a parallel schema. Decide in the review whether field names follow Opta's public conventions or StatsBomb open data where Opta detail is not public.
[ ] New raw events: shot_taken (with shot_speed and direction: left, center, right of goal as the viewer sees it), stoppage (reason, against, restart), whistle, crowd level as an explicit simulator event at a steady cadence (at least 2 Hz), so the strike cue and the crowd meter work Friday; phase_id on possession events; stoppage_id linking whistle, foul, card, restart; assist_by, key_pass, blocker on shots and passes; color on card; preempts: lower_third on goal and red card.
[ ] Pass quality on every pass: distance_m, completed, difficulty (0–1). Pick a simple documented formula; realistic ranges beat precision.
[ ] Per-player tracking from x, y and timestamps: speed_kmh, distance_km, top_speed_kmh; sprint and distance_milestone flags with configurable thresholds.
[ ] Derived state: shot ledger with chance_rank, 5-minute xG and shot windows, pressure_trend with a signed slope (the input to hold advice), momentum_label, zone namer, phase summary, last_stoppage, recap_points, player_focus, milestones.
[ ] Moment detector emitting Moment {moment_id, moment_type, beat, trigger_event_id, phase_id, stoppage_id, priority, snapshot} with the thresholds agreed in the review.
[ ] Storyline input: the simulator takes a storyline JSON plus a seed and guarantees each demo moment at a known minute (big chance ~23', stoppage with card ~31', goal ~41', half time, late chance, full time). Clubs, crests and squads are a static clubs.json in the repo; the squad-authoring agent is cut.
[ ] Script the hero scene into the storyline: a big chance whose result beat is followed by a goal within about 1.5 s on the same phase_id, so hold advice and supersession have something to show.
[ ] Reference match checked in: data/reference_match.jsonl (events) plus the derived-state checkpoints, regenerated by one command from the seed.
[ ] Offline mode replays the reference match end to end through detector and template agents with no network.
Thursday EOD done-criteria
1. Schema reviewed and change list committed as docs/SCHEMA_CHANGES.md.
2. Fixtures in the repo and referenced by the front end and agent tests.
3. python -m crq.sim --seed 42 --storyline data/storyline.json writes the reference match deterministically.
4. CRQ_OFFLINE=1 replay produces a Moment for each demo moment at the scripted minute.
5. Existing tests still pass; new events have at least one test each.
Friday, October 23: end-to-end demo
Friday the hat switches to platform. The goal is the non-negotiable working demo: reference match replay → three moments → scheduler → mandatory operator gate → overlay feed → viewer in three languages (EN, ES, HI) → half-time and full-time recap. Live Azure if the subscription and quota landed; offline mode otherwise, with the same code path.
[ ] Replay driver: GET /api/replay?seed=42&speed=1 starts the reference match on a clock; pause, resume and jump-to-minute; publishes events to Event Hubs when online, to an in-process queue when offline. It is a feed, not a file: each event is released 1–3 s after its action time (configurable, seeded jitter) and the strike always precedes its outcome, so the 2 s fan budget and the hold decision are tested against real timing. This is the demo control, the judges' play button, and the operator session's tool.
[ ] Strike cue on the direct path: shot_taken plus the current crowd level becomes a cue packet (team, direction, crowd level) on the viewer WebSocket in under 1 s, with no agent in between. The result-beat FanCard waits for the operator's decision on the matching proposal.
[ ] Layer scheduler, deterministic code with tests: layers full_screen, lower_third, ticker, badge; start and end on the match clock; no two items on one layer; earliest free gap; one story per window (60 s default); goal and red card preempt the lower third; writes ScreenState {on_air, queued, held}. No model in this path.
[ ] Hold advice from code: pressure_trend slope plus shots in the last window produce hold_advice {recommend: air | hold, reason, horizon_s} attached to the proposal before the Producer sees it. The Producer may phrase it; the call comes from state. Friday if it fits, Saturday at the latest.
[ ] Mandatory gate in the API: proposal states proposed → approved | held | overridden | superseded | sla_held; no auto-approve path, no setting that enables one; air only on approved or overridden. The brief's Decision.action enum is approve | hold | override | sla_hold; add supersede (actor supersession) so the log and the state machine agree.
[ ] SLA auto-hold: 20 s from proposed with no operator action moves the proposal to sla_held. In-process timer locally; Logic App when online (moved up from Sunday). Logged as a decision by actor sla.
[ ] Decision log: every state transition written to decisions with actor (operator, sla, supersession), timestamp, match clock, proposal id, and the edited line if any. GET /api/decisions.csv for download; this is the audit trail the Enterprise pitch names.
[ ] Event Hubs wired: producer in the replay driver, consumer in the API that updates MatchState, runs the detector and the scheduler. One consumer group per environment.
[ ] Cosmos wired: containers events, state, proposals, cards, decisions, evaluations; partition key match_id; managed identity, no keys. Nothing in the hot path waits on Cosmos.
[ ] Evaluation record on every agent call: snapshot, output, cites, routed model (from the router response, also on the trace span), latency, operator decision. Same table the Saturday Foundry run reads.
[ ] Supersession in the API: higher-priority moment on the same phase_id or stoppage_id marks pending lower-priority proposals superseded; the Producer sees them in ScreenState. The scripted hero scene must reproduce from the reference match.
[ ] Three languages in fixtures and replay: EN, ES, HI. Remove AR from the fixture files and the persona list.
[ ] Local azd up dry run against the sandbox the moment it exists; fix Bicep errors before the weekend.
[ ] Operator session support: replay with jump-to-moment ready for the 30-minute Black Box operator session; capture their comments on layers, hold times and the window rule as scheduler config changes.
Friday demo done-criteria
1. One command starts the replay and the three moments fire at the scripted minutes; the strike cue reaches the viewer in under 1 s.
2. A full replay never double-books a layer (asserted by a test over the whole reference match).
3. Operator approve, hold and override each change the overlay feed and the viewer; an untouched proposal moves to sla_held at 20 s; nothing airs without a decision.
4. decisions.csv downloads with every transition of the run, and evaluation records exist for every agent call.
5. The same run works with CRQ_OFFLINE=1 and, if quota arrived, against Foundry.
Saturday and Sunday: evaluation, deploy, hardening
Saturday is data and evaluation; Sunday is the public URL and the clean-room check. Anything not done by Sunday night is cut, not rushed into Monday.
Saturday, October 24
[ ] Evaluation dataset: for every moment in the reference match, the expected answer to each persona question, pulled from state (shooter, xG, zone, score, clock, stoppage reason). Export in the format Foundry evaluation accepts; hand to Swami by noon.
[ ] Planted-falsehood set: 8–10 copies of real snapshots, spread across the three moments, with one injected error each (wrong scorer, wrong minute, xG off by 0.3, wrong card color) and the expected catch. Result goes in the README table as "N injected, N caught."
[ ] Hold advice finished and tested if it did not land Friday; verify it says "hold" on the scripted hero scene and "air" on the late chance.
[ ] At least 20 tests green in CI: scheduler collisions, earliest free gap, preemption, SLA timer, state machine, detector thresholds, simulator determinism, cite resolution.
[ ] Tracking-style position stream in the reference match: ball and 22 players per tick, same clock and 0–100 pitch coordinates as the events, 4–10 Hz. The brief commits the pitch view for Saturday, so this stream is in scope; pick the tick rate in the Thursday review.
[ ] Check the 0.25-in-2-s "crowd rises" threshold against the actual crowd curve.
[ ] Milestones and player_focus verified against the reference match (first goal for club, 50th completed pass, 10 km covered).
Sunday, October 25
[ ] azd up to the public URL with the pre-loaded replay; judges can press play, pause and jump to the big chance without a login.
[ ] CI OIDC deploy on main working end to end; AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID set as Actions variables.
[ ] Logic App SLA verified in Azure and behaving exactly like the local timer; its holds appear in decisions with actor sla.
[ ] Cosmos indexing and TTL set so a day of judges' replays stays inside serverless limits; cost check in the portal.
[ ] Clean-room check of the repo: new code only, synthetic data only, no Black Box product code or TPS material, no secrets in history. Run a secret scan.
[ ] README, pipeline sections: testing instructions that work from a fresh clone on Windows and Linux; test count; one-command replay; enterprise section naming managed identity, the mandatory gate, the decision log download, and Bicep.
[ ] Fresh-machine test: someone else clones and runs CRQ_OFFLINE=1 from the README alone.
[ ] Confirm clubs.json and the storyline are the only squad sources in the repo; no squad-authoring code path remains.
Monday and Tuesday
[ ] Monday: keep the public URL up during video capture; reset the replay between takes; freeze main after the video.
[ ] Tuesday: final azd up, tag the release, confirm the testing instructions one last time before the noon Central submission.
Components to build
Fourteen components, all deterministic except the four agents the agents engineer owns; the pipeline engineer builds the twelve below. The flow is: Simulator → ReplayDriver → (Event Hubs) → Ingest/StatsEngine → MomentDetector → CueEmitter (direct to viewer) and the agent workflow → HoldAdvisor → LayerScheduler → ApprovalGate (SlaTimer, Supersessor) → Publisher → overlay feed and viewer, with DecisionLog and EvaluationRecorder written along the way.
The top row is Thursday's work; everything below it is Friday's. Two paths leave MomentDetector: the strike beat goes straight to the fan viewer through CueEmitter with no model, and the Moment goes to the agents, whose proposal is scheduled and then stopped at ApprovalGate until the operator, the SLA timer or a superseding goal moves it. Only the Publisher writes to the overlay feed, and it releases the FanCard's second beat in the same step; every transition through the gate lands in DecisionLog.
The top row is ingest. From the detector, the strike beat goes straight to the viewer with no model; the result beat runs through the agents, hold advice and the scheduler to the gate, and only an approved or overridden proposal reaches the publisher. The dashed lines are the two logs written along the way.
Component
Responsibility
Input
Output
Day
Key tests
Simulator
Seeded, storyline-driven match generator; Opta-style event records
storyline.json, seed
reference_match.jsonl events incl. shot_taken, stoppage, whistle, crowd
Thu
Same seed → identical file; each scripted moment at its minute
ReplayDriver
Plays a match file on a clock as a feed: 1–3 s release latency, strike before outcome; pause, jump, speed
Match file, speed
Events to Event Hubs or in-process queue; clock ticks
Fri
Jump lands on the exact event; speed 2× keeps ordering; no outcome ever precedes its strike
EventHubsBridge
Producer and checkpointed consumer; no-op in offline mode
Events
Events
Fri
Offline and online paths produce the same MatchState
StatsEngine
Folds events into MatchState: ledger, windows, pressure_trend, zones, player_focus, milestones
Event stream
MatchState + checkpoints
Thu
xG window sums; slope sign flips on the scripted pressure build
MomentDetector
Rules over MatchState; beats; priority; snapshot slice
MatchState delta
Moment
Thu
Big chance fires on strike and result; snapshot holds only its six pieces
CueEmitter
Direct path for beat one; no model
shot_taken + crowd
Cue packet on viewer WebSocket
Fri
Emitted < 1 s after the event in replay
HoldAdvisor
Pure function of pressure_trend, recent shots, clock
MatchState window, Moment
hold_advice {recommend, reason, horizon_s}
Fri/Sat
"hold" on the hero scene, "air" on the late chance
LayerScheduler
Layer choice, start/end, no collisions, earliest free gap, one story per window, preemption
OverlayProposal, ScreenState
Scheduled proposal, updated ScreenState
Fri
No overlap over a full replay; goal preempts lower third; gap search
ApprovalGate
Proposal state machine; the only way to air
Operator action, SLA, supersession
State transition + decisions row
Fri
No transition to air without approved or overridden; illegal transitions rejected
SlaTimer
20 s auto-hold; in-process locally, Logic App online
proposed event
sla_held transition
Fri (local), Sun (Logic App)
Fires at 20 s, cancelled by any operator action
Supersessor
Higher priority on same phase_id / stoppage_id supersedes pending
New Moment, pending proposals
superseded transitions, ScreenState note
Fri
Goal 1.5 s after chance result supersedes the chance proposal
Publisher
Writes approved items to the timed overlay feed and releases the matching FanCard
approved / overridden proposal
Overlay packet {layer, start, end, payload}; FanCard release
Fri
FanCard never precedes the decision
DecisionLog
Append-only audit of every transition
Transitions
decisions container; CSV export
Fri
Every transition in a replay has exactly one row
EvaluationRecorder
One row per agent call, routed model included
Agent call result
evaluations container; Foundry export
Fri
Row count equals agent calls in the run
Infra (Bicep, azd, CI)
Every resource as code, OIDC deploy, managed identity
—
Public URL, green pipeline
Fri dry run, Sun live
Fresh subscription to URL in one command
Two design rules hold across all of them. First, nothing on the viewer's beat-one path or the operator's gate path calls a model; latency and trust both come from that. Second, every component reads and writes Pydantic models that are also the fixture files, so the front end and the agents build against the same objects the pipeline emits.
Contracts this role owes the other three
Each row is something another engineer is blocked on until it lands. Fixtures are the contract until live wiring; whoever needs a field adds it to the fixture and tells the others.
Contract
Consumer
Form
Due
MatchState shape and WebSocket channel
Front end (direct-render components: score, clock, shot map, pressure sparkline)
Fixture JSON + Pydantic model
Thu mid-morning
Moment.snapshot per moment type
Agents engineer (the only thing agents see)
Typed slice per moment_type, documented in SCHEMA_CHANGES.md
Thu review
Priority table and supersession rules
Agents engineer, API
Table in docs/ + enforced in the API
Thu review
Strike cue packet {team, direction, crowd_level, clock}
Front end (deaf-fan beat one, crowd meter)
Fixture + WebSocket message type
Thu EOD
FanCard, OverlayProposal, RecapCard, PlayerLine records
Front end, agents engineer
Fixtures + models; patches per language land as each arrives
Thu EOD
Reference match with scripted minutes, hero scene included
Everyone (demo, tests, evaluation, operator session)
data/reference_match.jsonl + checkpoints, regenerated from seed
Thu EOD
ScreenState {on_air, queued, held} and layer timeline
Front end (overlay timeline, "on air now"), agents engineer (Producer input)
Pydantic model + WebSocket channel
Fri morning
hold_advice {recommend, reason, horizon_s} on the proposal
Agents engineer (Producer phrases it), front end (hold button hint)
Field on OverlayProposal
Fri, Sat latest
Proposal state machine and decisions row
Front end (button states), Swami (README, video audit scene)
States documented; GET /api/decisions.csv
Fri
Evaluation record row format, with routed model
Swami (Foundry evaluation), agents engineer (span attribute name)
One row per agent call in evaluations
Fri
Replay API (start, pause, jump)
Front end, video capture, judges, operator session
REST endpoints documented in README
Fri
Planted-falsehood set
Swami (evaluation table), agents engineer (verifier test)
Dataset file beside the reference match
Sat noon
Public URL and azd up
Swami (pitch, video, gallery comment), judges
Working deployment, README link
Sun
Microsoft stack learned inside this track
The learning goal is met by building, not by a research spike. Each service below has one concrete thing to get right and one thing to show the judges.
Service
Get right
Show
Azure Event Hubs
Partitioned producer with match_id as partition key; checkpointed consumer; consumer group per environment
Events flowing live in the portal metrics during the demo
Cosmos DB serverless
Partition key choice, point reads for state, TTL on replay data, no cross-partition queries in the hot path
Evaluation rows queryable in Data Explorer next to the Foundry run
Azure Container Apps
API and front end as two apps, ingress, scale-to-zero off for the demo, managed identity to Event Hubs and Cosmos
Public URL with no keys in config
Bicep + azd
One azd up provisions everything; environment per developer; outputs feed .env
Fresh subscription to running demo in one command
GitHub Actions + OIDC
Federated credential, no stored secrets, deploy on main
Green pipeline badge and deploy log in the repo
Microsoft Foundry (evaluation side)
Dataset format, custom faithfulness evaluator reading cites against snapshots, run history
Evaluation results on screen in the video
Agent Framework (observer)
Pair with the agents engineer on the executor API so detector and publisher executors sit in the same graph as the agents
One trace per moment_id end to end
Use the Microsoft Learn connector for current API surfaces rather than memory; agent-framework and azd both moved this year.
Dependencies and blockers
Nothing Thursday depends on Azure. From Friday on, three things gate the live path, and offline mode is the fallback for each.
Dependency
Owner
Needed by
Fallback if late
Azure sandbox subscription
Swami
Fri morning for azd up dry run
Friday demo runs CRQ_OFFLINE=1; deploy slips to Sat
Model router quota, 100K TPM, East US 2
Swami
Fri for live agents
Template agents; evaluation rows still written
OIDC federated credential + Actions variables
Swami (tenant), pipeline engineer (workflow)
Sun for CI deploy
Manual azd up from a laptop for the submission
Snapshot shape and priority table decisions
Thu review, all three engineers
Thu 10:00
Pipeline engineer decides and documents; others object in writing by noon
Deaf-fan hybrid (status strip + event cards) confirmed
Front-end engineer
Thu morning
Emit both continuous state and event cards; the front end picks
Squad-authoring agent output
Agents engineer
Sat
Hand-written clubs and storyline stay in the repo
Marketing name and logo decision
Swami
Mon for video and README
Neutral project name, "built by a team at Black Box"
Open questions for the Thursday review
[ ] Big-chance gate: fan card on every shot_taken with the proposal gated at chance_rank ≤ 3 or xg ≥ 0.25, or both gated the same way?
[ ] Event field names: Opta public conventions, or StatsBomb open data where Opta detail is not public? The simulator's field names follow the answer.
[ ] Layer set: are full_screen, lower_third, ticker, badge the right four, and which does the operator see as a timeline versus a queue? The operator session should settle this.
[ ] One-story window: 60 s default; is it per layer or across all layers?
[ ] Hold advice rule, written down so the evaluation can check it: trailing-window xG above what threshold, rising over how many windows, and how many seconds before advice flips back to "air"? Proposal: 20 s horizon, aligned with the SLA.
[ ] Goal default on SLA expiry: approve so the overlay never misses a goal, or hold like every other moment? Note that approve is an auto-air path; if chosen, it must be named in the pitch as the one exception.
[ ] Decision enum: confirm supersede is added to the brief's Decision.action so the state machine and the log match.
[ ] Crowd signal: this doc takes it as an explicit simulator event (steady cadence, scripted peaks at chances and goals). Confirm, or switch to deriving it from xG and pressure_trend.
[ ] Does the detector emit pressure_shift for Friday, or is it a Saturday moment? It needs two stable windows and may fire late in a scripted 90 minutes.
[ ] Evaluation record: score the operator's edited_line as well as the agent's original? Recommendation: yes, it gives a correction dataset for the pitch.
[ ] Expected-answer format for the evaluation dataset: one expected caption per question, or a rubric the Foundry evaluator scores against?
[ ] Cosmos: one container per record type, or one container with a type discriminator and match_id partition? One container is simpler for serverless and for the evaluation export.
[ ] Replay speed for the video: real time, or 2× with the three moments still 15 s apart on screen?
[ ] Tracking tick rate for the pitch view: 4, 5 or 10 Hz, and does the client interpolate?