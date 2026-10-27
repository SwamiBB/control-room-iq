# Evidence: every viewer, at the goal

Captured on **2026-10-28** from a local run of `main` with real models (`CRQ_OFFLINE=0`): the API and the web app
on one machine, one synthetic match replayed, and a headless browser holding one viewer page open per combination.
Every page was captured full-page at 1280 px wide at the same two moments, so the graphics did not move on between
tabs.

## What is here

| Path | What it shows |
| --- | --- |
| `contact-goal.png` | All 54 viewers at the goal, on one sheet |
| `contact-stats.png` | All 54 viewers at the scorer's stats panel, on one sheet |
| `goal/` | 54 screenshots taken when the goal graphic is on air |
| `stats/` | 54 screenshots taken about 9 seconds later, when the scorer's stats panel is on air |

## The 54 combinations

Persona × access × language × allegiance = 3 × 2 × 3 × 3:

| Setting | Values |
| --- | --- |
| Persona | `newcomer`, `fan`, `analyst` |
| Access | `none`, `deaf` (captions on) |
| Language | `en`, `es`, `hi` |
| Allegiance | `home`, `away`, `neutral` |

Files are named `<persona>-<access>-<language>-<allegiance>_goal.png` and `..._stats.png`, for example
`goal/fan-deaf-hi-neutral_goal.png`. The 54 viewers were captured in two batches of 27, each with its own replay of
the same match, so the goal line the model wrote differs between the batches.

## What was checked

Each batch was checked before it was kept; a batch that failed a check was taken again.

1. The goal line was written by a model, with no fallback to the template:
   - batch 1: *"GOAL — Finn Oakes gives Harbor City a 1-0 lead"*
   - batch 2: *"GOAL — Finn Oakes converts from close range to put Harbor City ahead"*
2. Every English viewer shows that line, or its own model-written version of it.
3. Every `deaf` viewer shows the caption card.
4. Every `_stats` shot shows the scorer's stats panel: *"Finn Oakes · 1 goal · 3 shots · xG 0.61 today"*.
5. Every page loaded, and every `_goal` shot shows the goal graphic.
6. In every `deaf` shot the caption card's last row, the score, is inside the image.

All 108 screenshots passed all six checks.

## How to read them

- **English viewers** show the model's goal line.
- **Spanish and Hindi viewers** show the goal from the language template, by design: a goal is high stakes, so other
  languages get the reviewed template line rather than a new model-written one. Items that only exist in English carry an "en inglés" / "अंग्रेज़ी में"
  badge.
- **Deaf viewers** get the caption card with every row of the moment, ending in the score.

All teams, players and events are synthetic.
