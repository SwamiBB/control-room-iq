"""CueEmitter: beat one of a big chance, straight to the viewer with no model in the path.

A `shot` moment (beat = strike) becomes a StrikeCue {team, direction, crowd_level, clock}. The deaf fan's
screen pulses and shows the cue within 1 s of the strike reaching the pipeline; the result caption
(FanCard) follows only after the operator decides on the matching proposal.
"""

from __future__ import annotations

from crq_schemas import MatchClock, Moment, MomentKind, StrikeCue


def strike_cue(m: Moment) -> StrikeCue | None:
    if m.kind != MomentKind.SHOT or m.beat != "strike":
        return None
    ev, clock = m.snapshot["event"], m.snapshot["clock"]
    return StrikeCue(cue_id=f"{m.moment_id}-cue", match_id=m.match_id, event_id=ev["event_id"], team=ev["team"],
                     direction=ev["attrs"].get("direction", "center"),
                     crowd_level=min(1.0, max(0.0, float(m.snapshot.get("crowd_level", 0.35)))),
                     clock=MatchClock(period=clock["period"], minute=clock["minute"], second=clock["second"]))
