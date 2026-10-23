from crq_schemas import EventType, MomentKind
from ingest.cues import strike_cue
from ingest.stats import StateFolder
from simulator.scripted import DATA_DIR, generate


def test_every_strike_becomes_a_cue_and_nothing_else_does():
    meta, events = generate(DATA_DIR / "storyline.json")
    folder = StateFolder(meta)
    by_id = {e.event_id: e for e in events}
    cues, strikes = [], sum(e.type == EventType.SHOT_TAKEN for e in events)
    for ev in events:
        for m in folder.apply(ev):
            cue = strike_cue(m)
            if m.kind != MomentKind.SHOT:
                assert cue is None
            elif cue:
                cues.append(cue)
    assert len(cues) == strikes
    for c in cues:
        ev = by_id[c.event_id]
        assert (c.team, c.direction, c.clock.minute, c.clock.second) == (
            ev.team, ev.attrs["direction"], ev.minute, ev.second)
        assert 0 <= c.crowd_level <= 1
    hero = next(c for c in cues if c.clock.minute == 41 and by_id[c.event_id].player == "har-10")
    assert hero.direction == "center"
