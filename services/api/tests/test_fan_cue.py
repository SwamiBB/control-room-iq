"""FanCue is code: built without any model call, and the strike beat that sends it runs no agents."""

import asyncio
from types import SimpleNamespace

import api.main as main
import pytest
from agents.workflow import fallback_explanation
from api.fan_cue import build_fan_cue
from api.main import ViewerPrefs, _handle_moment, _start_moment, hub
from api_factories import RecordingSocket, moment
from crq_schemas import FanCard, FanCue, Persona


class OrderCheckingPipeline:
    """Agent pipeline stand-in that records what viewers had already received when it was called."""

    def __init__(self, deaf: RecordingSocket) -> None:
        self.deaf = deaf
        self.cues_before_call: int | None = None

    async def process(self, m, **_kwargs):
        self.cues_before_call = len(self.deaf.of_type("fan_cue"))
        raise RuntimeError("stop after ordering check")


def _viewer(persona: Persona = Persona.FAN, access: str = "none") -> RecordingSocket:
    ws = RecordingSocket()
    hub.viewers[ws] = ViewerPrefs(persona=persona, access=access)
    return ws


def test_build_fan_cue_is_deterministic_and_carries_no_text():
    m = moment(beat="chance", play_ms=600_000, importance=0.72)
    cue = build_fan_cue(m, home_team="har")
    assert cue == build_fan_cue(m, home_team="har")
    assert (cue.cue_id, cue.kind, cue.play_ms, cue.team) == ("fc-mo-1", "chance", 600_000, "har")
    assert not {"line", "text", "caption"} & set(FanCue.model_fields)


def test_build_fan_cue_direction_flips_at_half_time():
    first = build_fan_cue(moment(beat="chance", period=1, team="har"), home_team="har")
    second = build_fan_cue(moment(beat="chance", period=2, team="har"), home_team="har")
    away = build_fan_cue(moment(beat="chance", period=1, team="nor"), home_team="har")
    assert (first.direction, second.direction, away.direction) == ("left_to_right", "right_to_left", "right_to_left")


def test_build_fan_cue_pulse_scales_with_importance():
    pulses = [build_fan_cue(moment(beat="chance", importance=i), home_team="har").pulse for i in (0.4, 0.6, 0.8, 0.95)]
    assert pulses == ["tap", "pulse", "wave", "surge"]


def test_chance_beat_sends_the_cue_and_runs_no_agents(monkeypatch):
    # The strike beat is code only (#50): the result beat a moment later writes the card.
    deaf, renderer = _viewer(access="deaf"), RecordingSocket()
    hub.feed.renderers.add(renderer)
    fake = OrderCheckingPipeline(deaf)
    monkeypatch.setattr(main, "pipeline", fake)
    asyncio.run(_start_moment(moment(beat="chance", play_ms=600_000)))
    assert fake.cues_before_call is None  # never called
    assert len(deaf.of_type("fan_cue")) == 1
    assert renderer.of_type("fan_cue")[0]["item"]["cue_id"] == "fc-mo-1"
    assert hub.moment_tasks == set()


def test_cue_goes_to_deaf_access_viewers_of_any_persona_only(monkeypatch):
    deaf, deaf_analyst, fan = _viewer(access="deaf"), _viewer(Persona.ANALYST, "deaf"), _viewer(Persona.FAN)
    monkeypatch.setattr(main, "pipeline", OrderCheckingPipeline(deaf))
    asyncio.run(_start_moment(moment(beat="chance")))
    assert len(deaf.of_type("fan_cue")) == len(deaf_analyst.of_type("fan_cue")) == 1 and fan.sent == []


def test_fan_card_from_the_pipeline_is_held_until_a_decision(monkeypatch):
    deaf = _viewer(access="deaf")
    m = moment(beat="result")
    card = FanCard(card_id="fc-1", match_id="m", moment_id=m.moment_id, play_ms=600_000, caption="Saved, low left")
    result = SimpleNamespace(explanation=fallback_explanation(m), line="Saved", variants=[], failures=[],
                             proposal=None, fan_card=card)

    async def process(_m, **_kwargs):
        return result

    monkeypatch.setattr(main.pipeline, "process", process)
    asyncio.run(_handle_moment(m))
    assert hub.results[m.moment_id]["fan_card"] == card.model_dump(mode="json")
    assert deaf.sent == [] and hub.feed.log == []


def test_result_and_unbeaten_moments_publish_no_cue(monkeypatch):
    deaf = _viewer(access="deaf")
    monkeypatch.setattr(main, "pipeline", OrderCheckingPipeline(deaf))
    for beat in ("result", "none"):
        with pytest.raises(RuntimeError, match="ordering check"):
            asyncio.run(_handle_moment(moment(f"mo-{beat}", beat=beat)))
    assert deaf.sent == [] and hub.feed.log == []
