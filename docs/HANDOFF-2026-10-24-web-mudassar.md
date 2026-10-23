## Front end: Mudassar's consolidated list

Last updated: Friday, October 23, 2026, late night (Central). Checked against `main` at `7c99cd1` (#24). Merges the
web items from `HANDOFF-2026-10-23-agents-web.md`, `HANDOFF-2026-10-24-goal-routine-metrics.md`,
`HANDOFF-2026-10-24-match-intelligence.md` and `HANDOFF-2026-10-24-fan-card.md`, plus preview before firing (#18)
and the Oct 22 front-end decisions (D1–D3). The API side of every item below is on `main` and tested; only the
screens are missing.

**Where the web is today:** `web/src/views/Operator.tsx` and `Viewer.tsx` are still the Oct 20 scaffold. The only web
code added since is the match intelligence panel and chips (#19, #23). The vite proxy already forwards every route
below.

| # | Task | Status | Why |
| --- | --- | --- | --- |
| **Must-have: the demo and the video do not work without these** | | | |
| 1 | **Bring `api.ts` and the scaffold up to the v0.2 contract** | Stale | Today the console sorts by the wrong priority, cannot drop, and starts a replay file that does not exist |
| 2 | **Viewer: four controls, packets, gate check** | Not started | The approved moment reaching each viewer is the story |
| 3 | **Deaf fan: strike pulse and caption card** | Not started | The hero scene |
| 4 | **Running order cards with gallery words** | Partly (old card) | What the graphics operator decides on |
| 5 | **Countdown, warning, hold and expiry** | Not started | Shows the AI never fires on its own |
| 6 | **Decision log with download** | Not started | Proof of every action, including holds by the timer |
| **Strong for judging** | | | |
| 7 | **Goal routine card with Fire all 3** | Not started | The control-room feedback we acted on |
| 8 | **Preview for: picked viewer groups** | Not started | The operator sees what each audience will get before firing |
| 9 | **Deliveries chips** | Not started | Shows the code checks choosing variant or template per language |
| 10 | **Scheduler timeline** | Not started | "The AI schedules the screen" needs to be visible |
| 11 | **Program output and pitch view** | Partly (text box) | The approved graphic on screen; the strike lit on the pitch |
| **Nice to have** | | | |
| 12 | Gallery metrics panel | Not started | Turnaround and workload for the README and video |
| 13 | Catch-up card ("What did I miss") | Not started | Viewer feature, quick to build |
| 14 | Multiviewer page for the video | Not started | One shot showing console and three viewers together |
| 15 | Translate the intel chip and card labels (es, hi) | Not started | Chips stay English for now; nice before the video |

### Details

**1. `api.ts` and the scaffold (do this first; about an hour)**
- `Proposal` type to the v0.2 `OverlayProposal`: `cue_id`, `t_in_ms` / `t_out_ms` (play time; `t_start_ms` /
  `t_end_ms` are legacy), `priority` (int, **1 = highest**: sort ascending, show as an integer), `evidence[]`,
  `hold_advice {recommend_hold, reason, until_play_ms}`, `fallback`, `meta {routing, model_served, latency_ms}`,
  `proposed_at`, `proposed_play_ms`, `warn_at`, `hold_at`, `package_id`, `package_seq`, `package_offset_ms`,
  `item_label`, `unsourced_numbers[]`.
- Status values: `proposed`, `approved`, `held`, `overridden`, `rejected`, `aired`, `expired`. The running order
  shows `proposed` and `held`.
- `decide()` must allow `"reject"` (shown as Drop).
- "Start replay" posts `data/match.jsonl`, which is not in the repo. Use `data/reference/match-042.jsonl` (also
  `match-007`, `match-101`).
- `state` messages carry `clock: {period, clock_ms, play_ms}`; use it for the match clock and for play-time math.
- Viewer history keys on `i.item_id`, which does not exist: key on `cue_id`.
- **There is no undo route.** Do not build an Undo button; Drop is the take-out verb.

**2. Viewer (`/ws/viewer?persona=&access=&lang=&allegiance=`)**
- Four controls: persona (newcomer / fan / analyst), access (none / deaf), language (English / Español / हिन्दी),
  side (home / away / neutral). Defaults: fan, none, English, neutral. Stop sending `persona=deaf`.
- Messages: `{type: "overlay", item: OverlayPacket}` and, for deaf access only, `{type: "fan_cue", cue: FanCue}`.
- **Upsert by `cue_id`**; a later packet with the same `cue_id` replaces the earlier one (preemption is a re-send with
  a shorter duration). Honor `replaces[]`.
- **Refuse any packet without `approval_id`, `approved_by` and `approved_at`**, and log the refusal in the browser
  console. This is the structural gate; the video shows it.
- Show `packet.line` as delivered. A Spanish or Hindi viewer may get `lang: "en"` when no checked version or template
  exists; show it as is. `verified: false` is an operator override: show an "Unverified" badge.
- Hindi needs a Devanagari font (for example Noto Sans Devanagari from Google Fonts); numbers stay Western digits.
- Supporters: `payload.perspective = {side, team, color, score: [ours, theirs], score_text}`. Use `color` and
  `score_text`; the framing is done by the API, never by the web.

**3. Deaf fan**
- `fan_cue`: pulse on the pitch edge the team is attacking. `direction` is `left_to_right` or `right_to_left`,
  `pulse` is `tap` / `pulse` / `wave` / `surge` (size and length), `crowd_level` 0–1, show for `hold_ms`.
- Caption card from `packet.fan_card` (lead graphic only), per `HANDOFF-2026-10-24-fan-card.md`:
  render **`packet.line`** as the caption (not `fan_card.caption`, which is the English reference); show
  `detail.shooter`, `zone`, `outcome`, chance quality and `score`. Translate zone, outcome, "about 1 in N" and the
  headings from a small en / es / hi table; hide the empty `context`.
- Event-driven cards plus a persistent live strip (score, clock), not a running caption stream (Oct 22 decision).

**4. Running order cards (`/ws/operator`)**
- Words from `docs/GALLERY-TERMS.md`: header **Graphics operator**; **Running order**; buttons **Fire**, **Hold**,
  **Drop**, **Override**; layer names without underscores (Lower third, Full screen, Stat panel, Ticker, Caption,
  Player tag).
- Each card: line, layer, evidence lines, faithfulness, routed model (`meta.model_served`, or "Template" when
  `fallback` is true or `meta.routing` is `template`), intel chips (`IntelChips`, already built), hold advice when
  `hold_advice.recommend_hold` (show `reason`).
- **Amber flag** when `unsourced_numbers` is not empty: "Number not from the data: 35", next to the chips.
- `override_line` goes only to `POST /proposals/{id}/override`; any other route returns 422.

**5. Countdown, warning, hold and expiry**
- Countdown on every open card from `hold_at`. From `warn_at`, or on `{type: "sla_warning", proposal_id, package_id,
  seconds_left, hold_at}`, turn the card amber: "Holds in 10 s".
- At `hold_at` the API holds it (`decided_by: "sla-timer"`); the card stays in the running order as Held.
- Held cards show "Expires at": `proposed_play_ms` plus the shelf life (`max_delay_ms`, at least 60 s) in play time.
  Remove the card when its status becomes `expired`. Firing an expired card returns 409; show a short notice.

**6. Decision log**
- `GET /decisions` (`entry_id`, `proposal_id`, `action`, `actor`, `at`, `reasoning`, `package_id`) with a
  **Download CSV** link to `GET /decisions.csv`.
- Labels: approved → Fired, rejected → Dropped, overridden → Overridden, actor `sla-timer` → Held by the timer,
  actor `expiry-rule` → Expired.

**7. Goal routine** (`HANDOFF-2026-10-24-goal-routine-metrics.md` §1)
- Group proposals that share `package_id` into one card titled **Goal routine**, items by `package_seq` with
  `item_label`, layer and "+25 s" from `package_offset_ms`.
- **Fire all 3** → `POST /packages/{id}/approve`; Hold and Drop → `/packages/{id}/hold` and `/reject`. Each item keeps
  its own small Drop (`POST /proposals/{id}/reject`). One countdown for the card (the lead's `hold_at`).

**8. Preview for** (#18)
- A row of chips on each card for the operator's picked viewer groups, plus "+ Pick", which opens a picker built from
  `GET /viewer-groups` (`key` such as `newcomer.none.hi.away`). Remember the picks per console in browser storage.
- `GET /proposals/{id}/preview?view=<key>&view=<key>` (up to 12) returns per group `text`, `source` (variant /
  template / base / override), `lang_shown`, `failures`, `perspective`. One line per group: the text, then
  "✓ variant", "↩ template" or "↩ English line" with the failure code.
- Refresh when the card changes and as the operator types an override (`&override_line=...`). Read-only: nothing airs.

**9. Deliveries chips**
- After each firing the console gets `{type: "deliveries", proposal_id, deliveries: [{persona, access, lang, source,
  failures}]}` (also `GET /deliveries`). Show one chip per viewer group on the fired card: ✓ variant, ↩ template,
  ↩ English, Override.

**10. Scheduler timeline**
- `GET /schedule` → `{clock, layers: {<layer>: {on_air[], queued[]}}, awaiting_decision[]}`. Rows = layers, x = play
  time; packets as blocks from `t_in_ms` to `t_out_ms`; awaiting decisions as outlined blocks. Poll every 2 s or
  refresh on each `proposal` message.
- Until `scheduler.py` lands, timing is "air now"; label those blocks "Unscheduled" rather than faking placement.

**11. Program output and pitch view**
- Program output: the aired graphic per layer (from `GET /schedule` `on_air`, or the `/ws/overlay` feed
  `{type: "packet" | "fan_cue", match_id, item}`), with the same gate check as the viewer.
- Pitch view (SVG 105 × 68, from the `state` messages): ball trail of the current phase, shot markers sized by xG,
  the strike highlighted. If time is short, shot markers and the strike highlight are enough.

**12. Gallery metrics** — poll `GET /metrics` every 5 s: median and p90 turnaround, override and drop rates,
decisions per 10 minutes, holds by the timer, expired, graphics per click.

**13. Catch-up card** — `GET /recap?minutes=10|20|30` → `{score, points[], text}`. Three buttons on the viewer.

**14. Multiviewer page** — `/multiview`: the console plus three viewer frames, for example Fan · English · neutral,
Fan · deaf · Español · home, Newcomer · हिन्दी · away. Used for one shot of the video.

### Already done, do not rebuild

- Match intelligence: `web/src/intel.ts`, `components/MatchIntel.tsx`, `components/IntelChips.tsx` (#19, #23). Move them
  into the new layout as they are.
- In the API: which line each viewer gets (checked variant, template or English), supporter framing, the caption
  card's facts, the goal routine's follow-ups, the timers, preview, metrics. The web only renders.
- `web/vite.config.ts` proxies every route above to `localhost:8000`.

### Run it locally (Windows PowerShell)

```powershell
$env:CRQ_OFFLINE = "1"; uvicorn api.main:app --reload          # terminal 1, from the repo root after pip install
cd web; npm install; npm run dev                                # terminal 2: /operator, /viewer
Invoke-RestMethod -Method Post -Uri http://localhost:8000/matches/replay -ContentType "application/json" `
  -Body '{"file": "data/reference/match-042.jsonl", "speed": 20}'
```

Open a viewer in a second browser window before firing, so deliveries and preview have a group to show.

### Open questions for Mudassar

- D3 two-tier blocking (`unsupported` hard block, `uncertain` acknowledged): the API does not enforce it yet. Keep the
  amber number flag as the only block signal for now.
- Strike-pulse direction: home attacks left to right in the first half, teams swap at half time. Fine for the pulse?

### If time runs short

Items 1–6 make the demo and the video; do them in order. Then 7 and 8. A plain table is acceptable for 10, and 11
can be shot markers only. Anything from 12–15 that does not ship comes out of the video script.
