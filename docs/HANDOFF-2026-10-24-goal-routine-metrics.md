## Goal routine, gallery words and metrics: what changed and what you need to do

Three changes on `feat/goal-package-metrics`. Everything is additive: no field or route was renamed or removed.

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

### 3. Gallery words

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
4. Decision log labels: approved → Fired, rejected → Dropped, actor `sla-timer` → Held by the timer.

### @Siranjeevi (agents)

- Nothing required. The producer still proposes one goal graphic; the API adds the follow-ups. If the
  producer prompt names follow-ups in `alternatives`, keep them out of the line itself.

### @Pranav (pipeline)

- Nothing required. The goal moment's `state.players[player]` must carry the scorer's goals, shots and xG
  at the moment of the goal, which the state engine already does.
