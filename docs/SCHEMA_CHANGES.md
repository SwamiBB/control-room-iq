# Schema change list (draft for the Thursday review)

Owner: pipeline engineer. Reviewers: agents engineer, front-end engineer. Status: **proposed**.

This list follows the Scenes & Data brief and the pipeline action list. Every change is **additive**: no
existing field in `packages/schemas` is renamed or removed before the demo. Once both reviewers confirm a
section, it is binding and changes only by addition. Whoever needs a new field adds it to the fixture first
and tells the other two.

Sections marked **Decide** are open questions; the proposal next to each is the default if nobody objects.

## 1. Rules

- **Shape.** Raw events stay one record per action, Opta-style: type, qualifiers, team and player IDs,
  period / minute / second, x and y, outcome. Type and qualifier names follow the
  [kloppy](https://kloppy.pysport.org/) event model, which maps to Opta, StatsBomb and Wyscout, so a
  licensed feed later is an adapter, not a rewrite. Our additions are extra types and qualifiers in the
  same shape (marked *ext* below).
- **Coordinates.** 0–100 on both axes. The team on the ball attacks toward x = 100. y = 0 is the
  attacking team's right touchline (Opta convention; to verify in review). Distances in metres assume a
  105 × 68 m pitch.
- **Clock.** `t_ms` (existing, from the start of the period) stays. Added: `minute` and `second` counting
  from the match kickoff, Opta-style (second half starts at 45:00; first-half stoppage time is 45+,
  still period 1).
- **Generation versus delivery.** The match file holds match-clock time only. The replay driver adds the
  1–3 s release latency and a `delivered_at` wall timestamp in the stream envelope, never in the file.
  The same seed therefore always produces a byte-identical reference match.
- **Languages.** EN, ES, HI in fixtures and replay. `ar` stays in the `Lang` type until after the demo
  (additive rule) but appears in no fixture.

## 2. Raw events (`MatchEvent`)

### 2.1 New fields (all optional, default null)

| Field | Type | On which events | Answers |
| --- | --- | --- | --- |
| `minute`, `second` | int | all | Opta-style clock |
| `phase_id` | str | every possession event (pass, carry, shot_taken, shot, take-on) | Who built it, how many passes |
| `stoppage_id` | str | whistle, foul, card, stoppage, restart | What was the foul, what follows |
| `frame` | int | all | Links the event to the tracking frame at the same time |

Qualifiers stay in the existing `attrs` dict. Keys below are the qualifier names.

### 2.2 New event types

| Type | kloppy equivalent | Qualifiers | Notes |
| --- | --- | --- | --- |
| `shot_taken` *ext* | none (strike before the Shot result) | `direction`: left / center / right of goal as the viewer sees it; `shot_speed_kmh`; `body_part` | Beat one of a big chance. Always precedes its `shot` and has the same `phase_id` |
| `stoppage` *ext* | none (summarises a dead ball) | `reason`: foul / offside / injury / ball_out; `against` (team ID); `restart`: free_kick / penalty / corner / throw_in / goal_kick / drop_ball / kick_off | Answers "why did play stop?" |
| `whistle` *ext* | none | `kind`: stop / restart / half_end / match_end | Makes the referee's whistle visible |
| `crowd` *ext* | none | `level` 0–1 | Steady cadence of at least 2 Hz, with scripted peaks on strikes, goals and decisions |
| `ball_out` | BallOut | `side`: touchline / byline | Stoppage reason source |
| `recovery` | Recovery | none | Loose-ball regain |
| `offside` *ext qualifier* | Pass result OFFSIDE | on `pass`: `outcome = fail`, `offside: true` | Stoppage reason source |

### 2.3 New qualifiers on existing types

| Type | Qualifier | Type | Notes |
| --- | --- | --- | --- |
| `pass` | `completed` | bool | Mirrors `outcome`; fixtures read it directly |
| `pass` | `key_pass` | bool | The last pass before a shot |
| `pass` | `set_piece` | free_kick / corner / throw_in / goal_kick / kick_off / none | kloppy SetPiece qualifier |
| `pass` | `distance_m`, `difficulty` (0–1) | float | Exist today; formula documented in the simulator |
| `shot` | `assist_by` | player ID | Who assisted |
| `shot` | `blocker` | player ID | Only when `outcome = blocked` |
| `shot` | `body_part` | foot / head / other | Rename-free: the existing `body` key stays; `body_part` is added beside it |
| `shot` | `set_piece` | as for pass | Goal from a set piece |
| `card` | `color` | yellow / second_yellow / red | Exists for yellow; second yellow and red are new |
| `shot` (goal), `card` (red) | `preempts` | `["lower_third"]` | Lets the scheduler cut the running lower third |

### 2.4 Tracking stream (pitch view only)

A separate file next to the match: `data/reference_tracking.jsonl`, one frame per line.

```json
{"frame": 1234, "period": 1, "t_ms": 308500, "ball": [62.1, 40.3], "players": {"har-07": [58.0, 37.2]}}
```

- **Decide:** tick rate. **Proposal: 4 Hz**, with the client interpolating. That is enough for the
  pitch view and the cheapest to generate.
- Same clock and the same 0–100 grid as the events, but in screen coordinates, not normalised per team:
  the home team attacks toward x = 100 in the first half and toward x = 0 in the second, so the pitch
  view draws frames as they come. Positions come from formation slots that stretch in possession and
  compact toward the ball out of it, plus the on-ball player, with steps capped by each player's pace.
- The file is gzipped (`reference_tracking*.jsonl.gz`, written with a fixed timestamp so the same seed
  gives a byte-identical file).
- Per-player `speed_kmh`, `distance_km` and `top_speed_kmh` are derived from these frames (section 3).
  This replaces today's carry-only distance, which comes out far below the usual 10–11 km per match.

## 3. Derived state (`MatchState`, new optional fields)

| Field | Shape | Answers |
| --- | --- | --- |
| `shot_ledger` | list of `{event_id, minute, team, player, xg, outcome, zone, chance_rank}` | Best chance of the match? Was that coming? |
| `windows` | per team: `{xg_5m, shots_5m}` over the trailing 5 minutes, recomputed each minute | Are they on top now? |
| `pressure_trend` | per team: `{value, slope}`, where `slope` is the signed change across the last two windows | Pattern or noise; input to hold advice |
| `momentum_label` | `home_on_top` / `away_on_top` / `even` / `swinging` | Later fan card |
| `zones` | the zone namer's output for the last event: e.g. `"edge of the box, left"` | From where, in plain language |
| `phase` | `{phase_id, team, passes, players, started_zone, started_minute}` | Build-up of a goal |
| `last_stoppage` | `{stoppage_id, reason, against, restart, card}` | What was the decision |
| `recap_points` | list of `{minute, kind, text_template, cites}` | Story of the half |
| `player_focus` | per player: `{distance_km, top_speed_kmh, sprints, passes_completed, xg}` | Player lines, milestones |
| `milestones` | list of `{player or team, kind, value, event_id}` | First goal, 50th completed pass, 10 km covered |

The zone namer splits x into own third / middle third / final third / box / six-yard box, and y into
left / center / right as the attacking team sees it.

## 4. Moments (`Moment`, new optional fields)

The existing `kind` is the moment type and `importance` stays. Added:

| Field | Type | Notes |
| --- | --- | --- |
| `beat` | `strike` / `result` / `single` | Big chance has two beats; most moments have one |
| `trigger_event_id` | str | The event that fired the moment |
| `phase_id`, `stoppage_id` | str | Used for supersession |
| `priority` | int 0–100 | From the priority table below |
| `snapshot` | dict | Only the slice the agents need for this moment type (4.2). The full `state` stays for now |

New `MomentKind` values: `stoppage`, `red_card`, `shot`.

As built (`services/ingest/ingest/stats.py`, `derive.py`):

- **Strike beat** = a `shot` moment on every `shot_taken`, `beat = strike`, priority 0, importance 0.25. It
  fires before anyone knows whether the shot is a big chance. Importance stays below the API's 0.3
  threshold, so it feeds the strike cue and never reaches the agents.
- **Result beat** = a `big_chance` moment (`beat = result`) when xG ≥ 0.25, or a `goal`. It shares
  `phase_id` with its strike.
- **Stoppage with a card** = a `stoppage` moment the moment play stops (priority 40, so the deaf fan
  learns why within 2 s), then a `card` (60) or `red_card` (90) moment on the same `stoppage_id` when the
  card is shown, which supersedes it.

### 4.1 Priority table and supersession (**Decide**; proposal)

| Moment | Priority | Produces |
| --- | --- | --- |
| Goal | 100 | Proposal (full screen, preempts the lower third) + fan card |
| Red card | 90 | Proposal (preempts the lower third) + fan card |
| Big chance, result beat | 70 | Proposal + fan card (released after the decision) |
| Stoppage with a card | 60 | Proposal + fan card |
| Stoppage | 40 | Fan card; a proposal only if the restart is a penalty or a free kick in the final third |
| Big chance, strike beat | — | Strike cue only, direct to the viewer, no agent |
| Pressure shift | 30 | After the demo |
| Milestone | 10 | Ticker proposal |

**Supersession:** a new moment with a higher priority on the same `phase_id` or `stoppage_id` marks
pending lower-priority proposals `superseded`. The hero scene tests this: a goal 1.5 s after the big
chance's result beat, on the same phase, supersedes the chance proposal.

**Decide:** the big-chance gate. **Proposal (as built):** a strike cue on every `shot_taken`; a proposal
only when xG ≥ 0.25. The `chance_rank` ≤ 3 alternative was dropped: the first three shots of any match
are always ranked 1–3, so it would propose every early shot.

### 4.2 Snapshot per moment type

| Moment | Snapshot holds |
| --- | --- |
| Big chance | The shot event (position, outcome); shooter; xG; shot history with timing (`shot_ledger` slice); pressure / momentum trend; score and clock |
| Goal | The goal event; scorer and body part / set piece; `phase` (build-up); `assist_by` and key pass; xG; score, clock, time remaining; trend before the goal |
| Stoppage | The stoppage event; reason, against, restart and zone; the linked card and the player's card history; score and clock |

Agents see only the snapshot, never raw events. Every `cites` entry must resolve to an event ID inside it.

## 5. Experience records (new models)

### 5.1 `StrikeCue` (beat one of a big chance, no model in the path)

`{cue_id, match_id, event_id, team, direction, crowd_level, clock: {period, minute, second}}`.
Due less than 1 s after `shot_taken` reaches the pipeline.

### 5.2 `FanCard`

| Field | Notes |
| --- | --- |
| `card_id`, `moment_id`, `lang`, `persona` | `persona` is the existing `accessibility` value, which now means the deaf fan (visual narration) |
| `caption` | Result line, e.g. "Saved! Kai Reed from the edge of the box" |
| `detail` | `{chance_quality, xg}`, where `chance_quality` is the plain-language form, e.g. "about 1 in 3 chances like this go in" |
| `context` | `{past, now, next}`, the later card |
| `cites`, `faithfulness` | As on `NarrativeVariant` |
| `released_by` | `decision_id`. Nothing reaches the fan without a Decision |
| `timing` | `{cue_due_ms: 1000, caption_due_ms: 2000}`: from `shot_taken` and from `shot` respectively |

### 5.3 `OverlayProposal` additions

`window_id` (one story per window), `hold_advice`, `evidence` (event IDs and the numbers taken from
them), `alternatives` (rejected layers, with reasons), and `provenance` (`{source: model | template,
agent, verdict, attempts, routed_model}`). `layer` and `priority` already exist; `OverlayLayer` gains
`badge`.

`HoldAdvice = {recommend: air | hold, reason, horizon_s}` is computed in code from state. The Producer
may word it but never decides it.

**Decide:** the hold rule. **Proposal:** recommend `hold` when the attacking team's trailing 5-minute xG
is ≥ 0.6 and its `pressure_trend.slope` > 0, or when it has 3 or more shots in the last 5 minutes.
`horizon_s` = 20, the same as the SLA. Otherwise recommend `air`. It must say `hold` on the hero scene
and `air` on the late chance.

### 5.4 `RecapCard`, `PlayerLine`

- `RecapCard {recap_id, match_id, kind: half_time | full_time, persona, lang, score, points: [{minute, text, cites}]}`
- `PlayerLine {player_id, name, number, team, line, stats, cites}`

### 5.5 `ScreenState`

`{match_id, t_ms, on_air: [...], queued: [...], held: [...]}`. Each item is
`{proposal_id, layer, t_start_ms, t_end_ms}`. Written only by the layer scheduler
(`services/api/api/scheduler.py`). Rules as built:

- **One match clock.** Scheduler times (and proposal `t_start_ms` / `t_end_ms` once scheduled) are in ms
  where period 1 is `t_ms` and period 2 is 60:00 + `t_ms`, so the two halves never collide.
- **No double booking.** One item per layer at a time; a `full_screen` also covers `lower_third`,
  `stat_panel` and `heatmap`. `ticker` and `badge` run alongside anything.
- **Earliest free gap** at or after the requested start.
- **One story per window.** At most one item per 60 s window across the story layers (`full_screen`,
  `lower_third`, `stat_panel`, `heatmap`); `window_id` is `<match_id>-w<window>`. The open question is
  settled as "across all story layers".
- **Preemption.** A goal or red card airs at once, cuts short the running item on the layers it covers,
  and pushes later queued items behind it.
- **Holds free the slot.** Approving a held or late proposal rebooks it from the current clock.
- A test replays all three reference matches with every proposal approved and asserts no layer is ever
  double-booked.

### 5.6 Proposal states and `Decision`

- `ProposalStatus` gains `superseded` and `sla_held`. The path to air is only through `approved` or
  `overridden`. There is no auto-approve state and no setting that enables one.
- New `Decision {decision_id, proposal_id, action, actor, operator, at, match_clock, edited_line,
  routed_model}`. `action` is approve / hold / override / sla_hold / supersede. `actor` is operator /
  sla / supersession. The existing `DecisionLogEntry` stays until the API moves to `Decision`.
- The brief writes the action as `superseded` and the action list as `supersede`. **As built:** the
  action is `supersede` and the resulting state is `superseded`.
- **As built** (`services/api/api/gate.py`): only actor `operator` can approve, override or hold;
  `sla_hold` is reserved for actor `sla` and acts only on untouched (`proposed`) proposals; `supersede` is
  reserved for actor `supersession` (a higher-priority moment on the same `phase_id` or `stoppage_id`). An
  operator can still approve a `held` or `sla_held` proposal. Illegal transitions return HTTP 409. Each
  transition writes one `Decision`; `GET /api/decisions.csv` exports them.

### 5.7 `EvaluationRecord` (one row per agent call)

`{record_id, match_id, moment_id, agent, routed_model, snapshot, output, cites, latency_ms,
decision_id, edited_line}`. This is the same table the Foundry evaluation reads.

## 6. Fixtures (the contract until live wiring)

Files go in `packages/schemas/fixtures/`. Each one validates against its Pydantic model in a test.

`match_state.json` · `moment_big_chance_strike.json` · `moment_big_chance_result.json` · `moment_goal.json` ·
`moment_stoppage_card.json` · `strike_cue.json` · `fan_card.json` (EN, ES, HI) · `overlay_proposal.json` ·
`screen_state.json` · `decision.json` · `evaluation_record.json`

## 7. Reference match

- `data/storyline.json` (seed plus the scripted moments) → `data/reference_match.jsonl` and
  `data/reference_tracking.jsonl`, regenerated by one command.
- Clubs and squads come from a static `data/clubs.json`.
- Scripted minutes: big chance ~23', stoppage with card ~31', goal ~41', half time, late chance, full time.
- Hero scene: a big chance saved at xG 0.38, then a goal about 1.5 s after the result beat, on the same `phase_id`.
- Two more scripted matches widen coverage for the evaluation dataset and the demo's match picker:
  `storyline_m2.json` (Riverside Athletic v Ironbridge FC, seed 7: offside, penalty, straight red, ten men
  equalise, 1–1) and `storyline_m3.json` (Northfield United v Harbor City, seed 101: 0–2 to 2–2 comeback
  with a second yellow). Clubs are four fictional sides in `data/clubs.json`. The simulator suppresses
  unscripted goals in all three, so each final score is the scripted one.
- Play between the scripted moments comes from the seeded engine. Each subsystem (play, crowd,
  stoppages, tracking) draws from its own random stream derived from the seed, so adding a new event
  type does not change the rest of the match.

## 8. Open questions for this review

1. Coordinate y-orientation: confirm the Opta convention (y = 0 on the attacking team's right).
2. Tracking tick rate: 4 Hz with client interpolation?
3. The big-chance gate, the priority table and the hold rule as proposed above?
4. One-story window: 60 s, per layer or across all layers?
5. `supersede` (action) versus `superseded` (state)?
6. Crowd as an explicit simulator event (this list) rather than derived from xG and pressure?
