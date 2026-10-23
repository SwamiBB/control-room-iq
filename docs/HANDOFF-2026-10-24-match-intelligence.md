# Handoff — match intelligence (expectation ii) through agents and front end

**Date:** October 24, 2026 · **From:** Swami · **Status:** merged to `main` as #19 (`81dc7a7`)

> Written on a `feat/match-intel-agents-web` branch in another session, on top of two earlier commits. Those two
> commits never reached this repo; #19 is the patch alone (it applies and passes on its own). If they held further
> work, it still needs to be brought in.

The organizers' expectation (ii) asks for real-time match intelligence: player identification with **speed and
distance threshold indicators**, **pass quality** (distance, accuracy, difficulty rating), and **ball and shot speed**.
The simulator already emits the raw numbers on events (`carry.speed_kmh`, `pass.distance_m / difficulty /
ball_speed_kmh`, `shot.speed_kmh`). This branch adds the contract for the stats engine's output and builds the
agents and front end on top of it. **The stats engine itself is unchanged: Pranav fills the new fields.**

## 1. Contract (additive to v0.2, every field has a default)

| Model | New fields |
| --- | --- |
| `ThresholdIndicator` (new) | `kind` (top_speed, sprint, distance, pass_difficulty, pass_distance, ball_speed, shot_speed), `player`, `team`, `event_id`, `play_ms`, `value`, `threshold`, `unit` (km/h, m, km, rating), `label` (display text; optional) |
| `PassQuality` (new) | `event_id`, `play_ms`, `team`, `player`, `receiver`, `distance_m`, `difficulty` 0–1, `difficulty_label` (routine, testing, hard, very_hard), `accuracy_pct` (passer's completion so far), `ball_speed_kmh`, `completed`, `progressive`, `key_pass` |
| `MomentMetrics` (new) | `player`, `player_speed_kmh`, `player_top_speed_kmh`, `player_distance_km`, `player_sprints`, `key_pass: PassQuality`, `shot_speed_kmh`, `ball_speed_kmh`, `thresholds[]` |
| `Moment` | `metrics: MomentMetrics | None` |
| `MatchState` | `last_pass: PassQuality | None`, `thresholds: list[ThresholdIndicator]` (recent crossings, newest last, keep ~20) |
| `PlayerStats` | `sprints`, `avg_pass_distance_m`, `avg_pass_difficulty`, `hard_passes_completed`, `max_shot_speed_kmh` |
| `TeamStats` | `pass_accuracy_pct`, `avg_pass_difficulty`, `max_shot_speed_kmh` |
| `ShotRecord` | `speed_kmh` |
| `MomentKind` | `standout_pass` (a completed pass rated very hard, or a long progressive key pass) |

## 2. What the stats engine needs to do (Pranav)

In `services/ingest/ingest/stats.py` (rules in `derive.py`):

1. **Passes:** on every pass, update `PlayerStats` pass averages and `hard_passes_completed`, `TeamStats.pass_accuracy_pct`
   and `avg_pass_difficulty`, and set `MatchState.last_pass` (with `accuracy_pct` = the passer's completion so far).
2. **Shots:** copy `attrs.speed_kmh` to `ShotRecord.speed_kmh`; update `max_shot_speed_kmh` on player and team.
3. **Running:** count `sprints` (proposal: a carry at or above 25 km/h). If tracking totals are available, use them for
   `distance_m`; carry-only distance is far too low to quote (the agents ignore distance under 1 km).
4. **Thresholds:** append a `ThresholdIndicator` to `MatchState.thresholds` when one is crossed. Proposed values, yours
   to tune: top speed ≥ 32 km/h (the existing `SPEED_THRESHOLD_KMH`), distance 5 / 10 km, pass difficulty ≥ 0.8,
   pass distance ≥ 40 m, shot speed ≥ 100 km/h.
5. **Moments:** fill `Moment.metrics` with the numbers that belong to that moment (the key pass for a chance or goal,
   the shot speed, the speed on the run, any thresholds crossed on it). Raise `standout_pass` moments (importance
   around 0.4 so they reach the producer, which needs ≥ 0.35).
6. **Labels:** `difficulty_label` bands are routine < 0.35 ≤ testing < 0.6 ≤ hard < 0.8 ≤ very_hard. The agents mirror this in
   `agents/match_intel.py` only for passes that arrive without a label; move the function to `derive.py` if you prefer.
7. **Own the readers:** once `Moment.metrics` is filled, please move the pure readers `intel_for`, `intel_numbers` and
   `team_pass_accuracy` from `agents/match_intel.py` into `ingest`. Today the API's variant checks import them from the
   agents package, so the code that decides which numbers a variant may quote lives with the system being checked, and
   `match_intel` imports `ingest.stats.SPEED_THRESHOLD_KMH` the other way. Moving them to the stats engine's owner
   removes both cross-workstream imports.

Until this lands, the agents derive what they can from state (speed moments get the threshold rebuilt from
`SPEED_THRESHOLD_KMH`; key pass, shot speed and thresholds are read from `last_pass`, `shots` and `thresholds` once filled).

## 3. Agents (merged in #19; Siranjeevi to review)

- `agents/match_intel.py`: reads `Moment.metrics` (or derives), produces plain facts, the allow-list of numbers, and the
  `intel` block for graphics. Pure code, no model calls.
- Every agent now receives `intel` = `{metrics, facts, team_pass_accuracy_pct}`. Prompts updated: explainer (why the run or
  pass mattered), narrator (one fact, exact), personalizer (newcomer words, fan one number, analyst the figures, deaf: who
  and where first), producer (speed → `player_tag`, standout pass → `stat_panel`).
- **Numbers from code:** after the producer runs, `payload.intel` is overwritten with the stats engine's numbers plus
  `names` (player id → display name) and `short` (one clause). The producer cannot put its own numbers there.
- Fallbacks: `speed_threshold` → `player_tag` (6 s), `standout_pass` → `stat_panel`; the analyst variant quotes the intel
  on those moments.
- `MomentResult.intel` carries the block; the API adds it to the operator `moment` message.
- `variant_checks.py`: intel numbers and team pass accuracy are on the allow-list, so a Spanish or Hindi variant may
  quote "33,1 km/h" or "84%"; a speed the stats engine never produced still fails `numbers`.
- **What a variant may quote** (review correction in #19): intel metrics and facts, `team_pass_accuracy_pct`, and the
  score, xG, possession, shots and minute from the state snapshot. The personalizer prompt now says exactly this.
  Anything else (passes, PPDA, pressures, momentum) fails the checks, and that viewer gets a template line. Before the
  correction the prompt allowed "any number in the state snapshot", so faithful variants were silently replaced.
- Not touched: the personalizer prompt still lists the old `accessibility` persona and Arabic; that rewrite is Siranjeevi's
  open item from `HANDOFF-2026-10-23-agents-web.md`.

## 4. Front end (merged in #19; Mudassar to fold into the new console)

- `web/src/intel.ts`: types mirroring the contract, formatters, `intelChips()` per register (newcomer / fan / analyst),
  speed and distance leaders, fastest shot.
- `web/src/components/MatchIntel.tsx`: operator panel — threshold indicator feed, top-speed and distance leaders (▲ marks
  a player over the speed threshold), pass-quality card (distance, passer accuracy, ball speed, difficulty bar and label),
  team pass accuracy, fastest shot.
- `web/src/components/IntelChips.tsx`: chips on proposal cards (`payload.intel`), moment cards (`intel`) and the viewer
  overlay (fan register for fan and deaf, analyst for analyst; names from `payload.intel.names`).
- Wired into the current `Operator.tsx` and `Viewer.tsx` with a few lines each. Both components are self-contained, so
  they drop into the rebuilt console as they are.

## 5. Tests

`services/agents/tests/test_match_intel.py` (20) and `services/api/tests/test_variant_checks_intel.py` (4, including
team pass accuracy allowed and PPDA refused). Existing fakes of `pipeline.process` accept the new `meta=` keyword.
Full offline suite on `main` after #19: 235 passed.

## 6. What you will see today

Until ingest fills `Moment.metrics`, intel is derived from state, so it shows mainly on `speed_threshold` moments
(speed and top speed), plus wherever the state already has a rated `last_pass` or a shot speed. Pass-quality and
shot-speed chips become common once section 2 lands.
