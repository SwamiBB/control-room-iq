"""#40: clubs are named the way viewers know them, never by a team id or code."""

import os

os.environ["CRQ_OFFLINE"] = "1"

from agents.workflow import _teams, club_names  # noqa: E402
from simulator.cli import build_meta  # noqa: E402

META = build_meta(42)  # Harbor City (har, HAR) v Northfield United (nfu, NFU)


def test_team_ids_and_codes_become_club_names():
    assert club_names("Finn Oakes puts har ahead", META) == "Finn Oakes puts Harbor City ahead"
    assert club_names("HAR lead 1-0 as Nfu press", META) == "Harbor City lead 1-0 as Northfield United press"


def test_only_whole_words_change():
    assert club_names("Harbor City hold on; Harbour lights", META) == "Harbor City hold on; Harbour lights"
    assert club_names("Cato Hart for nfu.", META) == "Cato Hart for Northfield United."


def test_the_agents_get_the_id_to_name_map():
    assert _teams(META) == {"har": "Harbor City", "nfu": "Northfield United"}
    assert _teams(None) == {}


def test_a_code_an_agent_writes_anyway_never_airs():
    import asyncio
    import json

    from agents.workflow import MomentPipeline, fallback_explanation
    from crq_schemas import MatchState, Moment, MomentKind, Persona, TeamStats

    state = MatchState(match_id="m", seq=1, period=1, t_ms=600_000, home=TeamStats(team="har"),
                       away=TeamStats(team="nfu"))
    m = Moment(moment_id="mo-1", match_id="m", t_ms=600_000, period=1, kind=MomentKind.BIG_CHANCE, importance=0.7,
               team="har", event_ids=["e-1"], summary="Big chance", state=state)
    sent = []

    class Agent:
        def __init__(self, name, reply):
            self.name, self.reply = name, reply

        async def run(self, text):
            sent.append((self.name, json.loads(text)))
            return type("R", (), {"text": self.reply, "raw_representation": None})()

    p = MomentPipeline()
    p.explainer = Agent("explainer", fallback_explanation(m).model_dump_json())
    p.narrator = Agent("narrator", "HAR go close as Nfu hold firm")
    p.producer = Agent("producer", json.dumps({"propose": True, "layer": "lower_third", "t_start_ms": 602_000,
                                               "t_end_ms": 612_000, "line": "har go close", "payload_json": "{}",
                                               "reasoning": "A clear chance.", "alternatives": []}))
    p.personalizer = Agent("personalizer", json.dumps({"variants": [
        {"persona": "fan", "access": "none", "lang": "en", "text": "har so close!", "cites": []}]}))
    p.localizer = Agent("localizer", json.dumps({"variants": [
        {"persona": "fan", "access": "none", "lang": "es", "text": "¡HAR, tan cerca!", "cites": []}]}))

    res = asyncio.run(p.process(m, meta=META, requests=[(Persona.FAN, "none", "en", {}),
                                                        (Persona.FAN, "none", "es", {})]))
    assert res.line == "Harbor City go close as Northfield United hold firm"
    assert res.proposal.line == "Harbor City go close"
    assert {v.text for v in res.variants} == {"Harbor City so close!", "¡Harbor City, tan cerca!"}
    assert all(payload["teams"] == {"har": "Harbor City", "nfu": "Northfield United"}
               for name, payload in sent if name in ("explainer", "narrator", "producer"))
