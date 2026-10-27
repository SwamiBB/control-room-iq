## Deaf fan's caption card: one card, facts filled in code

Decided Oct 23: one card per graphic (no per-language list, so no contract change). The API now builds it
in code for every result beat (a big chance's outcome, or a goal) and it airs inside the approved packet,
with the lead graphic only. Code: `services/api/api/fan_card.py`; tests: `test_fan_card.py`.

### What is on the card

| Field | Source | How the viewer shows it |
| --- | --- | --- |
| Caption | The packet's `line`, already delivered in the viewer's language (checked variant, template or English) | Render `packet.line`, **not** `fan_card.caption` (that is the English reference) |
| `detail.shooter` | Squad list | As written; names are never translated |
| `detail.zone` | Stats engine, `"<area>, <side>"` | Translate from the table below |
| `detail.outcome` | Shot outcome code | Translate: `goal`, `saved`, `off_target`, `blocked` |
| `detail.xg` / `detail.chance_quality` | Stats engine | English: use `chance_quality`. Spanish / Hindi: build "about 1 in N" from `xg` with the same rule (xG ≥ 0.5: "about round(xG×10) in 10"; else "about 1 in round(1/xG)", at least 2) |
| `detail.score` | Score at the moment | As written, Western digits |
| `context` (past / now / next) | Empty for now | Hide; the catch-up card covers "what did I miss" |

Zone areas: `six-yard box`, `inside the box`, `edge of the box`, `final third`, `middle third`, `own third`.
Sides: `left`, `right`, `centre`.

### @Mudassar

A small label table (en / es / hi) for the zone areas and sides, the four outcomes, the "about 1 in N"
sentence and the card headings. It can share the table planned for the intel chips. Native-speaker check
before the video.

### @Siranjeevi

Nothing required: `MomentResult.fan_card` is no longer needed from the workflow. If the workflow ever
builds one, the API uses it instead of the code-built card.

### Not building before submission

Producer takeover when the graphics operator is away. It is written into the README ("Human in the loop,
by design" and "Limits") and goes in the video as the next step.
