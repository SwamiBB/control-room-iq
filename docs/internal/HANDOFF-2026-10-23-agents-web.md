## Contract changes on #1 / API on #2: what you need to change

Hi Siranjeevi and Mudassar, a few contract changes landed on `feat/schemas-v0.2` (#1) after the Thursday plan, and the API side is up on `feat/api-v0.2` (#2). Here's what affects your workstreams. Questions welcome on the PRs.

### What changed in the contract (#1)
- **Personalization is now three independent axes:**
  - `Persona` = `newcomer | fan | analyst`: how much the viewer knows. `deaf` is no longer a persona.
  - `Access` = `none | deaf`: how they take in the match, applied on top of any persona. A deaf analyst is `persona=analyst, access=deaf`.
  - `Lang` = `en | es | hi`.
  - `NarrativeVariant` and `OverlayPacket` now carry `access`.
- **Supporter side:** `Allegiance` = `home | away | neutral`. Framing is code, not AI, so variants do **not** vary by side.
- **Approval scope:** the operator approves the line once, in English. A persona/access/language variant airs only if it passes code checks in the API. Otherwise the viewer gets a template line in their language, or the approved English line. Goals, cards and stoppages always use templates outside English.

---

### @Siranjeevi (agents)
1. **Variant requests are now `(persona, access, lang, focus)`.** I made the smallest change to `workflow.py` that keeps tests green (`9230aa4`); please review it.
2. **The personalizer prompt needs an update.** It still says `accessibility` and `ar`. Please:
   - add the `newcomer` persona (plain words; "about 1 in 3 chances like this go in" instead of xG),
   - add the `deaf` **access** rules (no sound references; where on the pitch, who, and the score after) for every persona,
   - return `access` on each variant.
3. **The API checks every variant before it airs** (`services/api/api/variant_checks.py`). The prompt should push the model to pass these, or its output is silently replaced by a template:
   - no numbers that aren't in the approved line or the moment's state (dropping numbers is fine),
   - player and club names exactly as given: no transliteration, no added players,
   - `cites` only from the moment's events,
   - length limits: lower third / stat panel 90, full screen 120, ticker 140, caption 160 characters,
   - no referee blame, betting, or injury talk,
   - an actual translation, not the English line copied,
   - `faithfulness` ≥ 0.8 whenever it's set.
4. **Fallback bug:** `fallback_variants` copies the English line into `es`/`hi` and labels it with that language. The API now catches this and sends the template instead, but please make the fallback emit only `en`, or nothing, for other languages.
5. **`MomentResult.fan_card: FanCard | None`:** the API reads this name and airs the card only inside an approved packet. Build it from the result-beat variant with `access=deaf`. One card per language, or English only for now?
6. **Don't build `FanCue` in the workflow.** The API builds it with plain code *before* calling the pipeline, so it airs within 1 s (`api/fan_cue.py`). Inside `process()` it would wait behind the model calls.
7. **Scheduler:** the API treats `t_out_ms > t_in_ms` as "placed by the scheduler" and otherwise uses an interim "air now" slot. Are `t_start_ms`/`t_end_ms` display-only from now on?

### @Mudassar (web)
1. **Viewer picker:** split it into four controls: persona (newcomer / fan / analyst), access (none / deaf), language, and side (home / away / neutral):
   `/ws/viewer?persona=&access=&lang=&allegiance=`
   `persona=deaf` still works for now (it's treated as fan + deaf) so the current UI doesn't break, but please move off it.
2. **Messages on `/ws/viewer`:**
   - `{type: "overlay", item: OverlayPacket}`. The packet carries `profile`, `access`, `lang`, `allegiance` and, for supporters, `payload.perspective = {side, team, color, score: [ours, theirs], score_text}`.
   - `{type: "fan_cue", cue: FanCue}`, sent to deaf-access viewers only. `Viewer.tsx` ignores it today.
   - Upsert by `cue_id`. The history list keys on `i.item_id`, which doesn't exist.
3. **Renderer feed `/ws/overlay`:** `{type: "packet" | "fan_cue", match_id, item}`.
4. **Rendering rules:**
   - refuse packets without `approval_id` / `approved_by` / `approved_at`,
   - `verified: false` means an operator override: show a badge?
   - a non-English viewer may get `lang: "en"` when no checked variant or template exists; show it as-is,
   - Hindi needs a Devanagari font; numbers stay Western digits,
   - order and highlight using `allegiance` + `perspective.color`.
5. **Console:**
   - `state` messages now carry `clock: {period, clock_ms, play_ms}`,
   - a new `deliveries` message after each approval lists, per viewer group, `source` (variant / template / base / override) and `failures`. Good for ✓ / ↩ chips per language,
   - new endpoints: `GET /schedule` (scheduler view), `GET /recap?minutes=10|20|30`, `GET /deliveries`, `GET /decisions.csv`, `POST /proposals/{id}/reject`. `decide()` in `api.ts` doesn't allow `"reject"` yet.
6. **`FanCue` direction:** home attacks left to right in the first half and teams swap at half time. OK for the pitch-edge pulse?

### Open for everyone
- Native-speaker review of the Spanish and Hindi template and score strings (`api/fallback_text.py`, `api/perspective.py`).
- Should `FanCard` be one per language? That would mean `OverlayPacket.fan_card` becomes a list, which is a contract change, so better decided this week.
