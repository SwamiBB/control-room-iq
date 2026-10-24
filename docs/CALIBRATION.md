# Simulator calibration

Event realism: mean over 200 seeded matches (seeds 1000–1199), compared with approximate top-flight ranges. The ranges are design targets for a football-realistic synthetic league, not validated benchmarks. Regenerate with `python -m simulator.cli calibrate --start 1000 --count 200`.

| Metric | Simulated | Target range | In range |
| --- | --- | --- | --- |
| Goals per match | 2.3 | 2.2–3.4 | yes |
| Shots per match | 24.1 | 20.0–32.0 | yes |
| Share of shots on target | 0.354 | 0.280–0.400 | yes |
| xG per shot | 0.099 | 0.080–0.130 | yes |
| Passes per match | 1035.4 | 800.0–1100.0 | yes |
| Pass completion | 0.847 | 0.760–0.880 | yes |
| Fouls per match | 20.8 | 16.0–30.0 | yes |
| Yellow cards per match | 3.2 | 2.0–5.0 | yes |
| Home possession share | 0.469 | 0.450–0.550 | yes |
| Distance per outfield player, full match (km) | 11.6 | 9.5–12.5 | yes |
| Top speed per outfield player (km/h) | 31.4 | 28.0–36.0 | yes |

Running rows come from the tracking stream of the reference match (storyline.json) (outfield players who played the full match).

11 of 11 checks in range.
