## Goal routine, gallery words and metrics: what changed and what you need to do

Four changes on `feat/goal-package-metrics`. Everything is additive: no field or route was renamed or removed.

### 1. Goal routine (one click fires three graphics)

When a goal is proposed, the API turns the producer's proposal into a **package** of three items, in
running order:

| Seq | Item label | Layer | Text from | Airs |
| --- | --- | --- | --- | --- |
| 0 | Goal graphic | full_screen | The producer agent (AI, gated as before) | When fired |
| 1 | Scorer stats | lower_third | Code, from the official stats | 25 s after firing (after the replay) |
| 2 | Ticker | ticker | Code, from the score and minute | When fired |

- New `OverlayProposal` fields: `proposed_at`, `package_id`, `package_seq`, `package_offset_ms`, `item_label`.
  `DecisionLogEntry.package_id` is new and is the last column of `decisions.csv`.
- New routes: `GET /packages/{package_id}` and `POST /packages/{package_id}/approve|hold|reject`. One call
  decides every open item in order. Each item still gets its own decision row and its own `approval_id`.
  Single items can still be decided on their own with the `/proposals/{id}/...` routes.
- The SLA timer cannot fire a package (403), the same as for single proposals.
- Code-built items have no AI variants: every viewer gets the English line. The deaf fan's caption
  (`fan_card`) travels with the lead graphic only.
- Code: `services/api/api/goal_package.py`; tests: `test_goal_package.py`, `test_packages_api.py`.

### 2. Gallery metrics

`GET /metrics` returns turnaround, error rate and workload for the match so far:

- `turnaround`: seconds from a proposal reaching the running order to being fired: `fired`, `median_s`, `p90_s`, `max_s`.
- `errors`: `decided`, `overridden`, `dropped`, `override_rate`, `drop_rate`, `fallback_proposals`,
  `deliveries` (variant/template/base/override counts) and `check_failures` (variant check codes).
- `workload`: `operator_decisions` (a package click counts once), `sla_holds`, `pending`, `play_minutes`,
  `decisions_per_10_min`, `packages_fired`, `graphics_per_click`.

Code: `services/api/api/metrics.py`; tests: `test_metrics.py`.

### 3. Warning before the hold, and expiry of stale graphics

- **Warning:** 10 s after a proposal reaches the running order with no decision, the console gets
  `{type: "sla_warning", proposal_id, package_id, seconds_left, hold_at}`. At 20 s the SLA timer holds it
  as before. Every proposal now also carries `warn_at` and `hold_at`, so the console can draw the countdown
  without waiting for the message.
- **Expiry:** a **held** graphic expires once the match has moved past it: more than its shelf life of play
  (the scheduler's `max_delay_ms`, at least 60 s) since it reached the running order. It gets status
  `expired`, a decision row with actor `expiry-rule`, and leaves the running order. Firing it after that
  returns 409. Graphics still awaiting a decision never expire; the SLA timer holds them first.
- Like the SLA timer, `expiry-rule` can never air anything (403). New proposal field: `proposed_play_ms`.
- `GET /metrics` → `workload.expired` counts them, apart from operator decisions.
- Code: `services/api/api/timing.py`; tests: `test_timing.py`, `test_sla_expiry_api.py`.

### 4. Gallery words

`docs/GALLERY-TERMS.md` has the role mapping and the on-screen words. The API is unchanged; only labels move.

---

### @Mudassar (console)

1. Rename on screen: "Next on screen" → **Running order**; Approve → **Fire**; Reject → **Drop**; header
   "Operator console" → **Graphics operator**. Layer names without underscores.
2. Group proposals that share a `package_id` into one card titled **Goal routine**, items listed by
   `package_seq` with `item_label`, layer and "+25 s" for `package_offset_ms`. One **Fire all 3** button
   calls `POST /packages/{id}/approve`; Hold and Drop call the same route with `hold` / `reject`. Each item
   keeps a small Drop so the operator can cut one before firing the rest.
3. Add a **Gallery metrics** panel polling `GET /metrics` every 5 s: median and p90 turnaround, override and
   drop rates, decisions per 10 minutes, SLA holds, graphics per click.
4. Decision log labels: approved → Fired, rejected → Dropped, actor `sla-timer` → Held by the timer,
   actor `expiry-rule` → Expired.
5. Countdown on every open card from `hold_at`. From `warn_at` (or on the `sla_warning` message) turn the
   card amber and show "Holds in 10 s". Held cards show "Expires at" from `proposed_play_ms` plus the
   shelf life; remove a card when its status becomes `expired`.

### @Siranjeevi (agents)

- Nothing required. The producer still proposes one goal graphic; the API adds the follow-ups. If the
  producer prompt names follow-ups in `alternatives`, keep them out of the line itself.

### @Pranav (pipeline)

- Nothing required. The goal moment's `state.players[player]` must carry the scorer's goals, shots and xG
  at the moment of the goal, which the state engine already does.
