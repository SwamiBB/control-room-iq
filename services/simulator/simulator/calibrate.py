"""Realism check: run the seeded engine over a fixed seed range and compare per-match averages with
approximate top-flight ranges, then check running distances and top speeds on the reference match.

The ranges are design targets for a football-realistic synthetic league, not validated benchmarks; the
README publishes the table as it comes out, failures included.

  python -m simulator.cli calibrate --start 1000 --count 200 --out docs/CALIBRATION.md
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable

from crq_schemas import EventType, MatchEvent

POSSESSION_TYPES = (EventType.PASS, EventType.CARRY, EventType.SHOT, EventType.KICKOFF, EventType.POSSESSION_CHANGE)

# (key, label, low, high): per match, both teams together unless stated
EVENT_TARGETS = [
    ("goals", "Goals per match", 2.2, 3.4),
    ("shots", "Shots per match", 20, 32),
    ("on_target_share", "Share of shots on target", 0.28, 0.40),
    ("xg_per_shot", "xG per shot", 0.08, 0.13),
    ("passes", "Passes per match", 800, 1100),
    ("pass_accuracy", "Pass completion", 0.76, 0.88),
    ("fouls", "Fouls per match", 16, 30),
    ("yellows", "Yellow cards per match", 2, 5),
    ("home_possession", "Home possession share", 0.45, 0.55),
]
TRACKING_TARGETS = [
    ("distance_km", "Distance per outfield player, full match (km)", 9.5, 12.5),
    ("top_speed_kmh", "Top speed per outfield player (km/h)", 28, 36),
]


def match_metrics(events: Iterable[MatchEvent], home_id: str) -> dict[str, float]:
    evs = list(events)
    shots = [e for e in evs if e.type == EventType.SHOT]
    passes = [e for e in evs if e.type == EventType.PASS]
    poss_ms: dict[str, int] = {}
    holder, last_t, last_period = None, 0, 1
    for e in evs:
        if e.period != last_period:
            last_t, last_period = 0, e.period
        if holder:
            poss_ms[holder] = poss_ms.get(holder, 0) + max(0, e.t_ms - last_t)
        last_t = e.t_ms
        if e.team and e.type in POSSESSION_TYPES:
            holder = e.team
    total = sum(poss_ms.values()) or 1
    return {
        "goals": sum(e.outcome == "goal" for e in shots),
        "shots": len(shots),
        "on_target_share": sum(e.outcome in ("goal", "saved") for e in shots) / (len(shots) or 1),
        "xg_per_shot": sum(float(e.attrs.get("xg", 0)) for e in shots) / (len(shots) or 1),
        "passes": len(passes),
        "pass_accuracy": sum(e.outcome == "success" for e in passes) / (len(passes) or 1),
        "fouls": sum(e.type == EventType.FOUL for e in evs),
        "yellows": sum(e.type == EventType.CARD and e.attrs.get("card", "yellow") == "yellow" for e in evs),
        "home_possession": poss_ms.get(home_id, 0) / total,
    }


def _row(key: str, label: str, lo: float, hi: float, values: list[float]) -> dict:
    mean = statistics.fmean(values) if values else float("nan")
    return {"key": key, "label": label, "mean": mean, "low": lo, "high": hi, "ok": lo <= mean <= hi, "n": len(values)}


def calibrate_engine(start: int, count: int) -> list[dict]:
    from .cli import build_meta  # local import: cli imports this module
    from .engine import MatchEngine

    per_match = []
    for seed in range(start, start + count):
        meta = build_meta(seed)
        per_match.append(match_metrics(MatchEngine(meta).run(), meta.home.team_id))
    return [_row(k, label, lo, hi, [m[k] for m in per_match]) for k, label, lo, hi in EVENT_TARGETS]


def calibrate_tracking(summary: dict[str, dict[str, float]], full_match: set[str]) -> list[dict]:
    """Running checks over outfield players who played the whole match."""
    rows = []
    for k, label, lo, hi in TRACKING_TARGETS:
        rows.append(_row(k, label, lo, hi, [v[k] for pid, v in summary.items() if pid in full_match]))
    return rows


def to_markdown(engine_rows: list[dict], start: int, count: int, tracking_rows: list[dict] | None = None,
                tracking_source: str = "") -> str:
    lines = ["# Simulator calibration", "",
             f"Event realism: mean over {count} seeded matches (seeds {start}–{start + count - 1}), compared with "
             "approximate top-flight ranges. The ranges are design targets for a football-realistic synthetic "
             "league, not validated benchmarks. Regenerate with "
             f"`python -m simulator.cli calibrate --start {start} --count {count}`.", "",
             "| Metric | Simulated | Target range | In range |", "| --- | --- | --- | --- |"]
    for r in engine_rows + (tracking_rows or []):
        fmt = "{:.3f}" if r["high"] <= 1 else "{:.1f}"
        lines.append(f"| {r['label']} | {fmt.format(r['mean'])} | {fmt.format(r['low'])}–{fmt.format(r['high'])} | "
                     f"{'yes' if r['ok'] else '**no**'} |")
    if tracking_rows:
        lines += ["", f"Running rows come from the tracking stream of {tracking_source} "
                      "(outfield players who played the full match)."]
    passed = sum(r["ok"] for r in engine_rows + (tracking_rows or []))
    lines += ["", f"{passed} of {len(engine_rows) + len(tracking_rows or [])} checks in range.", ""]
    return "\n".join(lines)
