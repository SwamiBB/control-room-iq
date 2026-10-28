# Evidence: every viewer, at the goal

Captured on **2026-10-28** from a local run with real models (`CRQ_OFFLINE=0`): the API and the web app on one
machine, one synthetic match replayed, and a headless browser holding one viewer page open per combination. Every
page was captured full-page at 1280 px wide at the same two moments, so the graphics did not move on between tabs.

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
the same match, so the English goal line the model wrote differs between the batches. Each home / away / neutral trio
is in one batch, so the three sides of a viewer always show the same goal.

| Batch | Viewers | English goal line (written by a model) |
| --- | --- | --- |
| 1 | every newcomer, and fan with standard access | *"Finn Oakes scores from 6.3 metres at 88.1 km/h — Harbor City lead Northfield United 1-0."* |
| 2 | fan with deaf access, and every analyst | *"GOAL — Finn Oakes fires Harbor City 1-0 ahead at 88.1 km/h"* |

## What was checked

Each batch was checked by script before it was kept:

1. The goal line was written by a model, with no fallback to the template.
2. Every English viewer shows that line, or its own model-written version of it.
3. Every `deaf` viewer shows the caption card, and its last row, the score, is inside the image.
4. Every `_stats` shot shows the scorer's stats panel.
5. Every page loaded, and every `_goal` shot shows the goal graphic.
6. The line above the goal graphic says what happened, in the viewer's language: *Goal* / *Gol* / *गोल*.
7. The ticker and the scorer's stats are in the viewer's language, with the same numbers and names as the English,
   and no "in English" badge.
8. Home and away viewers see the score from their side under the score bug; neutral viewers see the score bug alone.
9. No graphic carries a badge, and every Spanish and Hindi viewer has the goal line for their persona.
10. The page around the picture (title, pickers, help, notes) is in the viewer's language.
11. Analysts get the longer scorer stats; newcomers and fans the short line.
12. The scorer's stats panel takes the scorer's side colour, the same one as the score bug and the players.
13. No headline leaves the score alone on its last line.

## How to read them

- **English viewers** show the model's goal line.
- **Spanish and Hindi viewers** show the goal line for their persona: a goal is high stakes, so other languages get a
  fixed line built from the match data (scorer, club, minute and score; the analyst also gets the shot's xG) rather
  than a new model-written one:
  - newcomer: *"¡GOL! Finn Oakes marca para Harbor City. Marcador: 1–0"* /
    *"गोल! Finn Oakes ने Harbor City के लिए गोल किया। स्कोर: 1–0"*
  - fan: *"¡GOL de Finn Oakes para Harbor City en el minuto 42! Marcador 1–0"* /
    *"गोल! 42वें मिनट में Finn Oakes ने Harbor City के लिए गोल किया! स्कोर 1–0"*
  - analyst: *"Gol de Finn Oakes (Harbor City), minuto 42, xG del remate 0.45. Marcador 1–0"* /
    *"गोल: Finn Oakes (Harbor City), 42वाँ मिनट, शॉट का xG 0.45। स्कोर 1–0"*
- **The ticker** reads *"GOAL 42' · Harbor City 1–0 Northfield United · Finn Oakes"*, and *"GOL 42' · …"* /
  *"गोल 42' · …"* in Spanish and Hindi.
- **The scorer's stats** read *"Finn Oakes · 1 goal · 3 shots · xG 0.61 today"*, *"Finn Oakes · 1 gol · 3 remates ·
  xG 0.61 hoy"* and *"Finn Oakes आज · 1 गोल · 3 शॉट · xG 0.61"* (his xG for the match; the analyst's goal line gives
  that one shot's). Analysts also get his passing, distance and sprints: *"Finn Oakes today · 1 goal · 3 shots ·
  xG 0.61 · 15/18 passes · 5.42 km · 6 sprints"*. The panel's bar is in the scorer's side colour.
- **Home and away viewers** see their side's score under the score bug: *"HAR 1–0 up"* / *"NFU 0–1 down"*
  (*"HAR ganando 1–0"*, *"NFU 0–1 से पीछे"*).
- **Deaf viewers** get the caption card with every row of the moment, ending in the score.
- **The page** around the picture (the pickers, their help and the notes) is in the viewer's language too.

All teams, players and events are synthetic.

## Index

| Contact sheet: all 54 viewers at the goal | Contact sheet: all 54 viewers at the stats panel |
| --- | --- |
| <a href="contact-goal.png"><img src="contact-goal.png" width="400" alt="All 54 viewers at the goal"></a> | <a href="contact-stats.png"><img src="contact-stats.png" width="400" alt="All 54 viewers at the stats panel"></a> |

Galleries: [Newcomer](#newcomer-gallery) · [Fan](#fan-gallery) · [Analyst](#analyst-gallery)

### Newcomer

| # | Access | Language | Home | Away | Neutral |
| --- | --- | --- | --- | --- | --- |
| 1 | Standard | English | [goal](goal/newcomer-none-en-home_goal.png) · [stats](stats/newcomer-none-en-home_stats.png) | [goal](goal/newcomer-none-en-away_goal.png) · [stats](stats/newcomer-none-en-away_stats.png) | [goal](goal/newcomer-none-en-neutral_goal.png) · [stats](stats/newcomer-none-en-neutral_stats.png) |
| 2 | Standard | Spanish | [goal](goal/newcomer-none-es-home_goal.png) · [stats](stats/newcomer-none-es-home_stats.png) | [goal](goal/newcomer-none-es-away_goal.png) · [stats](stats/newcomer-none-es-away_stats.png) | [goal](goal/newcomer-none-es-neutral_goal.png) · [stats](stats/newcomer-none-es-neutral_stats.png) |
| 3 | Standard | Hindi | [goal](goal/newcomer-none-hi-home_goal.png) · [stats](stats/newcomer-none-hi-home_stats.png) | [goal](goal/newcomer-none-hi-away_goal.png) · [stats](stats/newcomer-none-hi-away_stats.png) | [goal](goal/newcomer-none-hi-neutral_goal.png) · [stats](stats/newcomer-none-hi-neutral_stats.png) |
| 4 | Deaf (captions) | English | [goal](goal/newcomer-deaf-en-home_goal.png) · [stats](stats/newcomer-deaf-en-home_stats.png) | [goal](goal/newcomer-deaf-en-away_goal.png) · [stats](stats/newcomer-deaf-en-away_stats.png) | [goal](goal/newcomer-deaf-en-neutral_goal.png) · [stats](stats/newcomer-deaf-en-neutral_stats.png) |
| 5 | Deaf (captions) | Spanish | [goal](goal/newcomer-deaf-es-home_goal.png) · [stats](stats/newcomer-deaf-es-home_stats.png) | [goal](goal/newcomer-deaf-es-away_goal.png) · [stats](stats/newcomer-deaf-es-away_stats.png) | [goal](goal/newcomer-deaf-es-neutral_goal.png) · [stats](stats/newcomer-deaf-es-neutral_stats.png) |
| 6 | Deaf (captions) | Hindi | [goal](goal/newcomer-deaf-hi-home_goal.png) · [stats](stats/newcomer-deaf-hi-home_stats.png) | [goal](goal/newcomer-deaf-hi-away_goal.png) · [stats](stats/newcomer-deaf-hi-away_stats.png) | [goal](goal/newcomer-deaf-hi-neutral_goal.png) · [stats](stats/newcomer-deaf-hi-neutral_stats.png) |

### Fan

| # | Access | Language | Home | Away | Neutral |
| --- | --- | --- | --- | --- | --- |
| 1 | Standard | English | [goal](goal/fan-none-en-home_goal.png) · [stats](stats/fan-none-en-home_stats.png) | [goal](goal/fan-none-en-away_goal.png) · [stats](stats/fan-none-en-away_stats.png) | [goal](goal/fan-none-en-neutral_goal.png) · [stats](stats/fan-none-en-neutral_stats.png) |
| 2 | Standard | Spanish | [goal](goal/fan-none-es-home_goal.png) · [stats](stats/fan-none-es-home_stats.png) | [goal](goal/fan-none-es-away_goal.png) · [stats](stats/fan-none-es-away_stats.png) | [goal](goal/fan-none-es-neutral_goal.png) · [stats](stats/fan-none-es-neutral_stats.png) |
| 3 | Standard | Hindi | [goal](goal/fan-none-hi-home_goal.png) · [stats](stats/fan-none-hi-home_stats.png) | [goal](goal/fan-none-hi-away_goal.png) · [stats](stats/fan-none-hi-away_stats.png) | [goal](goal/fan-none-hi-neutral_goal.png) · [stats](stats/fan-none-hi-neutral_stats.png) |
| 4 | Deaf (captions) | English | [goal](goal/fan-deaf-en-home_goal.png) · [stats](stats/fan-deaf-en-home_stats.png) | [goal](goal/fan-deaf-en-away_goal.png) · [stats](stats/fan-deaf-en-away_stats.png) | [goal](goal/fan-deaf-en-neutral_goal.png) · [stats](stats/fan-deaf-en-neutral_stats.png) |
| 5 | Deaf (captions) | Spanish | [goal](goal/fan-deaf-es-home_goal.png) · [stats](stats/fan-deaf-es-home_stats.png) | [goal](goal/fan-deaf-es-away_goal.png) · [stats](stats/fan-deaf-es-away_stats.png) | [goal](goal/fan-deaf-es-neutral_goal.png) · [stats](stats/fan-deaf-es-neutral_stats.png) |
| 6 | Deaf (captions) | Hindi | [goal](goal/fan-deaf-hi-home_goal.png) · [stats](stats/fan-deaf-hi-home_stats.png) | [goal](goal/fan-deaf-hi-away_goal.png) · [stats](stats/fan-deaf-hi-away_stats.png) | [goal](goal/fan-deaf-hi-neutral_goal.png) · [stats](stats/fan-deaf-hi-neutral_stats.png) |

### Analyst

| # | Access | Language | Home | Away | Neutral |
| --- | --- | --- | --- | --- | --- |
| 1 | Standard | English | [goal](goal/analyst-none-en-home_goal.png) · [stats](stats/analyst-none-en-home_stats.png) | [goal](goal/analyst-none-en-away_goal.png) · [stats](stats/analyst-none-en-away_stats.png) | [goal](goal/analyst-none-en-neutral_goal.png) · [stats](stats/analyst-none-en-neutral_stats.png) |
| 2 | Standard | Spanish | [goal](goal/analyst-none-es-home_goal.png) · [stats](stats/analyst-none-es-home_stats.png) | [goal](goal/analyst-none-es-away_goal.png) · [stats](stats/analyst-none-es-away_stats.png) | [goal](goal/analyst-none-es-neutral_goal.png) · [stats](stats/analyst-none-es-neutral_stats.png) |
| 3 | Standard | Hindi | [goal](goal/analyst-none-hi-home_goal.png) · [stats](stats/analyst-none-hi-home_stats.png) | [goal](goal/analyst-none-hi-away_goal.png) · [stats](stats/analyst-none-hi-away_stats.png) | [goal](goal/analyst-none-hi-neutral_goal.png) · [stats](stats/analyst-none-hi-neutral_stats.png) |
| 4 | Deaf (captions) | English | [goal](goal/analyst-deaf-en-home_goal.png) · [stats](stats/analyst-deaf-en-home_stats.png) | [goal](goal/analyst-deaf-en-away_goal.png) · [stats](stats/analyst-deaf-en-away_stats.png) | [goal](goal/analyst-deaf-en-neutral_goal.png) · [stats](stats/analyst-deaf-en-neutral_stats.png) |
| 5 | Deaf (captions) | Spanish | [goal](goal/analyst-deaf-es-home_goal.png) · [stats](stats/analyst-deaf-es-home_stats.png) | [goal](goal/analyst-deaf-es-away_goal.png) · [stats](stats/analyst-deaf-es-away_stats.png) | [goal](goal/analyst-deaf-es-neutral_goal.png) · [stats](stats/analyst-deaf-es-neutral_stats.png) |
| 6 | Deaf (captions) | Hindi | [goal](goal/analyst-deaf-hi-home_goal.png) · [stats](stats/analyst-deaf-hi-home_stats.png) | [goal](goal/analyst-deaf-hi-away_goal.png) · [stats](stats/analyst-deaf-hi-away_stats.png) | [goal](goal/analyst-deaf-hi-neutral_goal.png) · [stats](stats/analyst-deaf-hi-neutral_stats.png) |

## Newcomer gallery

Open a block to see the home, away and neutral viewers side by side. Select an image for the full-size file.

<details open>
<summary><b>Newcomer · Standard · English</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/newcomer-none-en-home_goal.png"><img src="goal/newcomer-none-en-home_goal.png" width="300" alt="newcomer-none-en-home goal"></a></td><td><a href="goal/newcomer-none-en-away_goal.png"><img src="goal/newcomer-none-en-away_goal.png" width="300" alt="newcomer-none-en-away goal"></a></td><td><a href="goal/newcomer-none-en-neutral_goal.png"><img src="goal/newcomer-none-en-neutral_goal.png" width="300" alt="newcomer-none-en-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/newcomer-none-en-home_stats.png"><img src="stats/newcomer-none-en-home_stats.png" width="300" alt="newcomer-none-en-home stats"></a></td><td><a href="stats/newcomer-none-en-away_stats.png"><img src="stats/newcomer-none-en-away_stats.png" width="300" alt="newcomer-none-en-away stats"></a></td><td><a href="stats/newcomer-none-en-neutral_stats.png"><img src="stats/newcomer-none-en-neutral_stats.png" width="300" alt="newcomer-none-en-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Newcomer · Standard · Spanish</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/newcomer-none-es-home_goal.png"><img src="goal/newcomer-none-es-home_goal.png" width="300" alt="newcomer-none-es-home goal"></a></td><td><a href="goal/newcomer-none-es-away_goal.png"><img src="goal/newcomer-none-es-away_goal.png" width="300" alt="newcomer-none-es-away goal"></a></td><td><a href="goal/newcomer-none-es-neutral_goal.png"><img src="goal/newcomer-none-es-neutral_goal.png" width="300" alt="newcomer-none-es-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/newcomer-none-es-home_stats.png"><img src="stats/newcomer-none-es-home_stats.png" width="300" alt="newcomer-none-es-home stats"></a></td><td><a href="stats/newcomer-none-es-away_stats.png"><img src="stats/newcomer-none-es-away_stats.png" width="300" alt="newcomer-none-es-away stats"></a></td><td><a href="stats/newcomer-none-es-neutral_stats.png"><img src="stats/newcomer-none-es-neutral_stats.png" width="300" alt="newcomer-none-es-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Newcomer · Standard · Hindi</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/newcomer-none-hi-home_goal.png"><img src="goal/newcomer-none-hi-home_goal.png" width="300" alt="newcomer-none-hi-home goal"></a></td><td><a href="goal/newcomer-none-hi-away_goal.png"><img src="goal/newcomer-none-hi-away_goal.png" width="300" alt="newcomer-none-hi-away goal"></a></td><td><a href="goal/newcomer-none-hi-neutral_goal.png"><img src="goal/newcomer-none-hi-neutral_goal.png" width="300" alt="newcomer-none-hi-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/newcomer-none-hi-home_stats.png"><img src="stats/newcomer-none-hi-home_stats.png" width="300" alt="newcomer-none-hi-home stats"></a></td><td><a href="stats/newcomer-none-hi-away_stats.png"><img src="stats/newcomer-none-hi-away_stats.png" width="300" alt="newcomer-none-hi-away stats"></a></td><td><a href="stats/newcomer-none-hi-neutral_stats.png"><img src="stats/newcomer-none-hi-neutral_stats.png" width="300" alt="newcomer-none-hi-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Newcomer · Deaf (captions) · English</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/newcomer-deaf-en-home_goal.png"><img src="goal/newcomer-deaf-en-home_goal.png" width="300" alt="newcomer-deaf-en-home goal"></a></td><td><a href="goal/newcomer-deaf-en-away_goal.png"><img src="goal/newcomer-deaf-en-away_goal.png" width="300" alt="newcomer-deaf-en-away goal"></a></td><td><a href="goal/newcomer-deaf-en-neutral_goal.png"><img src="goal/newcomer-deaf-en-neutral_goal.png" width="300" alt="newcomer-deaf-en-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/newcomer-deaf-en-home_stats.png"><img src="stats/newcomer-deaf-en-home_stats.png" width="300" alt="newcomer-deaf-en-home stats"></a></td><td><a href="stats/newcomer-deaf-en-away_stats.png"><img src="stats/newcomer-deaf-en-away_stats.png" width="300" alt="newcomer-deaf-en-away stats"></a></td><td><a href="stats/newcomer-deaf-en-neutral_stats.png"><img src="stats/newcomer-deaf-en-neutral_stats.png" width="300" alt="newcomer-deaf-en-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Newcomer · Deaf (captions) · Spanish</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/newcomer-deaf-es-home_goal.png"><img src="goal/newcomer-deaf-es-home_goal.png" width="300" alt="newcomer-deaf-es-home goal"></a></td><td><a href="goal/newcomer-deaf-es-away_goal.png"><img src="goal/newcomer-deaf-es-away_goal.png" width="300" alt="newcomer-deaf-es-away goal"></a></td><td><a href="goal/newcomer-deaf-es-neutral_goal.png"><img src="goal/newcomer-deaf-es-neutral_goal.png" width="300" alt="newcomer-deaf-es-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/newcomer-deaf-es-home_stats.png"><img src="stats/newcomer-deaf-es-home_stats.png" width="300" alt="newcomer-deaf-es-home stats"></a></td><td><a href="stats/newcomer-deaf-es-away_stats.png"><img src="stats/newcomer-deaf-es-away_stats.png" width="300" alt="newcomer-deaf-es-away stats"></a></td><td><a href="stats/newcomer-deaf-es-neutral_stats.png"><img src="stats/newcomer-deaf-es-neutral_stats.png" width="300" alt="newcomer-deaf-es-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Newcomer · Deaf (captions) · Hindi</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/newcomer-deaf-hi-home_goal.png"><img src="goal/newcomer-deaf-hi-home_goal.png" width="300" alt="newcomer-deaf-hi-home goal"></a></td><td><a href="goal/newcomer-deaf-hi-away_goal.png"><img src="goal/newcomer-deaf-hi-away_goal.png" width="300" alt="newcomer-deaf-hi-away goal"></a></td><td><a href="goal/newcomer-deaf-hi-neutral_goal.png"><img src="goal/newcomer-deaf-hi-neutral_goal.png" width="300" alt="newcomer-deaf-hi-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/newcomer-deaf-hi-home_stats.png"><img src="stats/newcomer-deaf-hi-home_stats.png" width="300" alt="newcomer-deaf-hi-home stats"></a></td><td><a href="stats/newcomer-deaf-hi-away_stats.png"><img src="stats/newcomer-deaf-hi-away_stats.png" width="300" alt="newcomer-deaf-hi-away stats"></a></td><td><a href="stats/newcomer-deaf-hi-neutral_stats.png"><img src="stats/newcomer-deaf-hi-neutral_stats.png" width="300" alt="newcomer-deaf-hi-neutral stats"></a></td></tr>
</table>

</details>

[Back to index](#index)

## Fan gallery

Open a block to see the home, away and neutral viewers side by side. Select an image for the full-size file.

<details open>
<summary><b>Fan · Standard · English</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/fan-none-en-home_goal.png"><img src="goal/fan-none-en-home_goal.png" width="300" alt="fan-none-en-home goal"></a></td><td><a href="goal/fan-none-en-away_goal.png"><img src="goal/fan-none-en-away_goal.png" width="300" alt="fan-none-en-away goal"></a></td><td><a href="goal/fan-none-en-neutral_goal.png"><img src="goal/fan-none-en-neutral_goal.png" width="300" alt="fan-none-en-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/fan-none-en-home_stats.png"><img src="stats/fan-none-en-home_stats.png" width="300" alt="fan-none-en-home stats"></a></td><td><a href="stats/fan-none-en-away_stats.png"><img src="stats/fan-none-en-away_stats.png" width="300" alt="fan-none-en-away stats"></a></td><td><a href="stats/fan-none-en-neutral_stats.png"><img src="stats/fan-none-en-neutral_stats.png" width="300" alt="fan-none-en-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Fan · Standard · Spanish</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/fan-none-es-home_goal.png"><img src="goal/fan-none-es-home_goal.png" width="300" alt="fan-none-es-home goal"></a></td><td><a href="goal/fan-none-es-away_goal.png"><img src="goal/fan-none-es-away_goal.png" width="300" alt="fan-none-es-away goal"></a></td><td><a href="goal/fan-none-es-neutral_goal.png"><img src="goal/fan-none-es-neutral_goal.png" width="300" alt="fan-none-es-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/fan-none-es-home_stats.png"><img src="stats/fan-none-es-home_stats.png" width="300" alt="fan-none-es-home stats"></a></td><td><a href="stats/fan-none-es-away_stats.png"><img src="stats/fan-none-es-away_stats.png" width="300" alt="fan-none-es-away stats"></a></td><td><a href="stats/fan-none-es-neutral_stats.png"><img src="stats/fan-none-es-neutral_stats.png" width="300" alt="fan-none-es-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Fan · Standard · Hindi</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/fan-none-hi-home_goal.png"><img src="goal/fan-none-hi-home_goal.png" width="300" alt="fan-none-hi-home goal"></a></td><td><a href="goal/fan-none-hi-away_goal.png"><img src="goal/fan-none-hi-away_goal.png" width="300" alt="fan-none-hi-away goal"></a></td><td><a href="goal/fan-none-hi-neutral_goal.png"><img src="goal/fan-none-hi-neutral_goal.png" width="300" alt="fan-none-hi-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/fan-none-hi-home_stats.png"><img src="stats/fan-none-hi-home_stats.png" width="300" alt="fan-none-hi-home stats"></a></td><td><a href="stats/fan-none-hi-away_stats.png"><img src="stats/fan-none-hi-away_stats.png" width="300" alt="fan-none-hi-away stats"></a></td><td><a href="stats/fan-none-hi-neutral_stats.png"><img src="stats/fan-none-hi-neutral_stats.png" width="300" alt="fan-none-hi-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Fan · Deaf (captions) · English</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/fan-deaf-en-home_goal.png"><img src="goal/fan-deaf-en-home_goal.png" width="300" alt="fan-deaf-en-home goal"></a></td><td><a href="goal/fan-deaf-en-away_goal.png"><img src="goal/fan-deaf-en-away_goal.png" width="300" alt="fan-deaf-en-away goal"></a></td><td><a href="goal/fan-deaf-en-neutral_goal.png"><img src="goal/fan-deaf-en-neutral_goal.png" width="300" alt="fan-deaf-en-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/fan-deaf-en-home_stats.png"><img src="stats/fan-deaf-en-home_stats.png" width="300" alt="fan-deaf-en-home stats"></a></td><td><a href="stats/fan-deaf-en-away_stats.png"><img src="stats/fan-deaf-en-away_stats.png" width="300" alt="fan-deaf-en-away stats"></a></td><td><a href="stats/fan-deaf-en-neutral_stats.png"><img src="stats/fan-deaf-en-neutral_stats.png" width="300" alt="fan-deaf-en-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Fan · Deaf (captions) · Spanish</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/fan-deaf-es-home_goal.png"><img src="goal/fan-deaf-es-home_goal.png" width="300" alt="fan-deaf-es-home goal"></a></td><td><a href="goal/fan-deaf-es-away_goal.png"><img src="goal/fan-deaf-es-away_goal.png" width="300" alt="fan-deaf-es-away goal"></a></td><td><a href="goal/fan-deaf-es-neutral_goal.png"><img src="goal/fan-deaf-es-neutral_goal.png" width="300" alt="fan-deaf-es-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/fan-deaf-es-home_stats.png"><img src="stats/fan-deaf-es-home_stats.png" width="300" alt="fan-deaf-es-home stats"></a></td><td><a href="stats/fan-deaf-es-away_stats.png"><img src="stats/fan-deaf-es-away_stats.png" width="300" alt="fan-deaf-es-away stats"></a></td><td><a href="stats/fan-deaf-es-neutral_stats.png"><img src="stats/fan-deaf-es-neutral_stats.png" width="300" alt="fan-deaf-es-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Fan · Deaf (captions) · Hindi</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/fan-deaf-hi-home_goal.png"><img src="goal/fan-deaf-hi-home_goal.png" width="300" alt="fan-deaf-hi-home goal"></a></td><td><a href="goal/fan-deaf-hi-away_goal.png"><img src="goal/fan-deaf-hi-away_goal.png" width="300" alt="fan-deaf-hi-away goal"></a></td><td><a href="goal/fan-deaf-hi-neutral_goal.png"><img src="goal/fan-deaf-hi-neutral_goal.png" width="300" alt="fan-deaf-hi-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/fan-deaf-hi-home_stats.png"><img src="stats/fan-deaf-hi-home_stats.png" width="300" alt="fan-deaf-hi-home stats"></a></td><td><a href="stats/fan-deaf-hi-away_stats.png"><img src="stats/fan-deaf-hi-away_stats.png" width="300" alt="fan-deaf-hi-away stats"></a></td><td><a href="stats/fan-deaf-hi-neutral_stats.png"><img src="stats/fan-deaf-hi-neutral_stats.png" width="300" alt="fan-deaf-hi-neutral stats"></a></td></tr>
</table>

</details>

[Back to index](#index)

## Analyst gallery

Open a block to see the home, away and neutral viewers side by side. Select an image for the full-size file.

<details open>
<summary><b>Analyst · Standard · English</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/analyst-none-en-home_goal.png"><img src="goal/analyst-none-en-home_goal.png" width="300" alt="analyst-none-en-home goal"></a></td><td><a href="goal/analyst-none-en-away_goal.png"><img src="goal/analyst-none-en-away_goal.png" width="300" alt="analyst-none-en-away goal"></a></td><td><a href="goal/analyst-none-en-neutral_goal.png"><img src="goal/analyst-none-en-neutral_goal.png" width="300" alt="analyst-none-en-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/analyst-none-en-home_stats.png"><img src="stats/analyst-none-en-home_stats.png" width="300" alt="analyst-none-en-home stats"></a></td><td><a href="stats/analyst-none-en-away_stats.png"><img src="stats/analyst-none-en-away_stats.png" width="300" alt="analyst-none-en-away stats"></a></td><td><a href="stats/analyst-none-en-neutral_stats.png"><img src="stats/analyst-none-en-neutral_stats.png" width="300" alt="analyst-none-en-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Analyst · Standard · Spanish</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/analyst-none-es-home_goal.png"><img src="goal/analyst-none-es-home_goal.png" width="300" alt="analyst-none-es-home goal"></a></td><td><a href="goal/analyst-none-es-away_goal.png"><img src="goal/analyst-none-es-away_goal.png" width="300" alt="analyst-none-es-away goal"></a></td><td><a href="goal/analyst-none-es-neutral_goal.png"><img src="goal/analyst-none-es-neutral_goal.png" width="300" alt="analyst-none-es-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/analyst-none-es-home_stats.png"><img src="stats/analyst-none-es-home_stats.png" width="300" alt="analyst-none-es-home stats"></a></td><td><a href="stats/analyst-none-es-away_stats.png"><img src="stats/analyst-none-es-away_stats.png" width="300" alt="analyst-none-es-away stats"></a></td><td><a href="stats/analyst-none-es-neutral_stats.png"><img src="stats/analyst-none-es-neutral_stats.png" width="300" alt="analyst-none-es-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Analyst · Standard · Hindi</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/analyst-none-hi-home_goal.png"><img src="goal/analyst-none-hi-home_goal.png" width="300" alt="analyst-none-hi-home goal"></a></td><td><a href="goal/analyst-none-hi-away_goal.png"><img src="goal/analyst-none-hi-away_goal.png" width="300" alt="analyst-none-hi-away goal"></a></td><td><a href="goal/analyst-none-hi-neutral_goal.png"><img src="goal/analyst-none-hi-neutral_goal.png" width="300" alt="analyst-none-hi-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/analyst-none-hi-home_stats.png"><img src="stats/analyst-none-hi-home_stats.png" width="300" alt="analyst-none-hi-home stats"></a></td><td><a href="stats/analyst-none-hi-away_stats.png"><img src="stats/analyst-none-hi-away_stats.png" width="300" alt="analyst-none-hi-away stats"></a></td><td><a href="stats/analyst-none-hi-neutral_stats.png"><img src="stats/analyst-none-hi-neutral_stats.png" width="300" alt="analyst-none-hi-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Analyst · Deaf (captions) · English</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/analyst-deaf-en-home_goal.png"><img src="goal/analyst-deaf-en-home_goal.png" width="300" alt="analyst-deaf-en-home goal"></a></td><td><a href="goal/analyst-deaf-en-away_goal.png"><img src="goal/analyst-deaf-en-away_goal.png" width="300" alt="analyst-deaf-en-away goal"></a></td><td><a href="goal/analyst-deaf-en-neutral_goal.png"><img src="goal/analyst-deaf-en-neutral_goal.png" width="300" alt="analyst-deaf-en-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/analyst-deaf-en-home_stats.png"><img src="stats/analyst-deaf-en-home_stats.png" width="300" alt="analyst-deaf-en-home stats"></a></td><td><a href="stats/analyst-deaf-en-away_stats.png"><img src="stats/analyst-deaf-en-away_stats.png" width="300" alt="analyst-deaf-en-away stats"></a></td><td><a href="stats/analyst-deaf-en-neutral_stats.png"><img src="stats/analyst-deaf-en-neutral_stats.png" width="300" alt="analyst-deaf-en-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Analyst · Deaf (captions) · Spanish</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/analyst-deaf-es-home_goal.png"><img src="goal/analyst-deaf-es-home_goal.png" width="300" alt="analyst-deaf-es-home goal"></a></td><td><a href="goal/analyst-deaf-es-away_goal.png"><img src="goal/analyst-deaf-es-away_goal.png" width="300" alt="analyst-deaf-es-away goal"></a></td><td><a href="goal/analyst-deaf-es-neutral_goal.png"><img src="goal/analyst-deaf-es-neutral_goal.png" width="300" alt="analyst-deaf-es-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/analyst-deaf-es-home_stats.png"><img src="stats/analyst-deaf-es-home_stats.png" width="300" alt="analyst-deaf-es-home stats"></a></td><td><a href="stats/analyst-deaf-es-away_stats.png"><img src="stats/analyst-deaf-es-away_stats.png" width="300" alt="analyst-deaf-es-away stats"></a></td><td><a href="stats/analyst-deaf-es-neutral_stats.png"><img src="stats/analyst-deaf-es-neutral_stats.png" width="300" alt="analyst-deaf-es-neutral stats"></a></td></tr>
</table>

</details>

<details>
<summary><b>Analyst · Deaf (captions) · Hindi</b></summary>

<table>
<tr><th></th><th>Home</th><th>Away</th><th>Neutral</th></tr>
<tr><th>Goal</th><td><a href="goal/analyst-deaf-hi-home_goal.png"><img src="goal/analyst-deaf-hi-home_goal.png" width="300" alt="analyst-deaf-hi-home goal"></a></td><td><a href="goal/analyst-deaf-hi-away_goal.png"><img src="goal/analyst-deaf-hi-away_goal.png" width="300" alt="analyst-deaf-hi-away goal"></a></td><td><a href="goal/analyst-deaf-hi-neutral_goal.png"><img src="goal/analyst-deaf-hi-neutral_goal.png" width="300" alt="analyst-deaf-hi-neutral goal"></a></td></tr>
<tr><th>Stats</th><td><a href="stats/analyst-deaf-hi-home_stats.png"><img src="stats/analyst-deaf-hi-home_stats.png" width="300" alt="analyst-deaf-hi-home stats"></a></td><td><a href="stats/analyst-deaf-hi-away_stats.png"><img src="stats/analyst-deaf-hi-away_stats.png" width="300" alt="analyst-deaf-hi-away stats"></a></td><td><a href="stats/analyst-deaf-hi-neutral_stats.png"><img src="stats/analyst-deaf-hi-neutral_stats.png" width="300" alt="analyst-deaf-hi-neutral stats"></a></td></tr>
</table>

</details>

[Back to index](#index)
