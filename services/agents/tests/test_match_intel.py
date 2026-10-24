"""Match intelligence (expectation ii) through the agents: speed and distance thresholds, pass quality, ball and
shot speed. The numbers come from the stats engine; these tests check the agents only read and forward them."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402
from agents.match_intel import (  # noqa: E402
    difficulty_label,
    intel_facts,
    intel_for,
    intel_numbers,
    intel_payload,
    intel_short,
)
from agents.workflow import (  # noqa: E402
    MomentPipeline,
    ProducerDecision,
    fallback_proposal,
    fallback_variants,
    with_intel,
)
from crq_schemas import (  # noqa: E402
    Explanation,
    MatchState,
    Moment,
    MomentKind,
    MomentMetrics,
    OverlayLayer,
    OverlayProposal,
    PassQuality,
    Persona,
    PlayerStats,
    ShotRecord,
    TeamStats,
    ThresholdIndicator,
)

KEY_PASS = PassQuality(event_id="e-40", play_ms=2_460_000, team="har", player="har-08", receiver="har-09",
                       distance_m=38.5, difficulty=0.82, difficulty_label="very_hard", accuracy_pct=87.0,
                       ball_speed_kmh=64.7, progressive=True, key_pass=True)
SPRINT = ThresholdIndicator(kind="top_speed", player="har-09", team="har", event_id="e-41", play_ms=2_461_000,
                            value=33.1, threshold=32, unit="km/h", label="33.1 km/h (over 32)")
NAMES = {"har-08": "Eli Arden", "har-09": "Ade Pike"}


def _state(**overrides) -> MatchState:
    fields = {"match_id": "m", "seq": 1, "period": 1, "t_ms": 2_461_000, "play_ms": 2_461_000,
              "home": TeamStats(team="har", passes=200, passes_completed=170), "away": TeamStats(team="nor"),
              "players": {"har-09": PlayerStats(player_id="har-09", team="har", top_speed_kmh=33.1, distance_m=6240,
                                                sprints=11)}}
    return MatchState(**(fields | overrides))


def _moment(kind=MomentKind.STANDOUT_PASS, metrics: MomentMetrics | None = None, **overrides) -> Moment:
    fields = {"moment_id": "mo-1", "match_id": "m", "play_ms": 2_461_000, "t_ms": 2_461_000, "period": 1,
              "kind": kind, "importance": 0.5, "team": "har", "player": "har-09", "event_ids": ["e-40", "e-41"],
              "summary": "Eli Arden finds Ade Pike", "state": _state(), "metrics": metrics}
    return Moment(**(fields | overrides))


def _engine_metrics() -> MomentMetrics:
    return MomentMetrics(player="har-09", player_speed_kmh=33.1, player_top_speed_kmh=33.1, player_distance_km=6.24,
                         player_sprints=11, key_pass=KEY_PASS, thresholds=[SPRINT])


# ---------- reading the stats engine ----------

def test_stats_engine_metrics_are_used_as_given():
    m = _moment(metrics=_engine_metrics())
    assert intel_for(m) is m.metrics


def test_without_stats_engine_metrics_the_state_snapshot_still_yields_intel():
    shot = ShotRecord(event_id="e-41", play_ms=2_461_000, period=1, t_ms=2_461_000, team="har", player="har-09",
                      xg=0.38, outcome="saved", speed_kmh=104.2)
    m = _moment(kind=MomentKind.BIG_CHANCE, state=_state(last_pass=KEY_PASS, thresholds=[SPRINT], shots=[shot]))
    got = intel_for(m)
    assert got is not None
    assert got.shot_speed_kmh == 104.2
    assert got.key_pass == KEY_PASS
    assert got.thresholds == [SPRINT]
    assert got.player_top_speed_kmh is None  # running totals belong to speed moments only


def test_a_moment_with_no_intel_returns_none():
    m = _moment(kind=MomentKind.CARD, player=None, state=_state(players={}))
    assert intel_for(m) is None
    assert intel_payload(None) is None and intel_facts(None) == [] and intel_short(None) is None


def test_a_pass_to_someone_else_is_not_this_moments_key_pass():
    other = KEY_PASS.model_copy(update={"event_id": "e-10", "receiver": "har-11"})
    got = intel_for(_moment(kind=MomentKind.BIG_CHANCE, state=_state(last_pass=other)))
    assert got is None or got.key_pass is None


@pytest.mark.parametrize(("difficulty", "label"), [(0.1, "routine"), (0.35, "testing"), (0.6, "hard"),
                                                    (0.82, "very_hard")])
def test_difficulty_bands(difficulty, label):
    assert difficulty_label(difficulty) == label


# ---------- facts the agents may quote ----------

def test_facts_carry_names_units_and_the_exact_numbers():
    facts = intel_facts(_engine_metrics(), lambda pid: NAMES.get(pid or "", pid or ""))
    joined = " | ".join(facts)
    assert facts[0] == "Ade Pike: top speed 33.1 km/h (over 32)"  # the stats engine's own label is kept
    assert not any("running at" in f or "top speed so far" in f for f in facts)  # no repeat of the threshold
    assert "Eli Arden pass 38.5 m, difficulty 0.82 (very hard), passer accuracy 87%, ball speed 64.7 km/h" in joined
    assert "to Ade Pike" in joined
    assert "distance covered 6.2 km, 11 sprints" in joined


def test_every_quoted_number_is_on_the_allow_list():
    allowed = intel_numbers(_engine_metrics())
    for n in (33.1, 32, 6.24, 6240, 11, 38.5, 0.82, 82, 87.0, 64.7):
        assert n in allowed


# ---------- proposals ----------

def _expl(m: Moment) -> Explanation:
    return Explanation(moment_id=m.moment_id, headline="h", why_it_matters="w", pattern="individual",
                       cites=m.event_ids, confidence=0.5)


def test_speed_threshold_fallback_is_a_lower_third_carrying_the_intel():
    m = _moment(kind=MomentKind.SPEED_THRESHOLD, metrics=_engine_metrics(), importance=0.35)
    p = fallback_proposal(m, _expl(m), "Ade Pike hits 33.1 km/h")
    assert p is not None and p.layer == OverlayLayer.LOWER_THIRD
    assert p.payload["intel"]["thresholds"][0]["value"] == 33.1
    assert p.payload["intel"]["short"] == "top speed 33.1 km/h"


def test_standout_pass_fallback_is_a_stat_panel_with_pass_quality():
    m = _moment(metrics=_engine_metrics())
    p = fallback_proposal(m, _expl(m), "Eli Arden splits the line")
    assert p is not None and p.layer == OverlayLayer.STAT_PANEL
    kp = p.payload["intel"]["key_pass"]
    assert (kp["distance_m"], kp["difficulty"], kp["difficulty_label"], kp["accuracy_pct"], kp["ball_speed_kmh"]) == (
        38.5, 0.82, "very_hard", 87.0, 64.7)


def test_producer_cannot_write_its_own_intel_numbers():
    m = _moment(metrics=_engine_metrics())
    model_made = OverlayProposal(proposal_id="p-1", match_id="m", moment_id="mo-1", layer=OverlayLayer.STAT_PANEL,
                                 line="x", reasoning="r", payload={"intel": {"shot_speed_kmh": 150}, "title": "Pass"})
    p = with_intel(model_made, m)
    assert p.payload["title"] == "Pass"
    assert "shot_speed_kmh" not in p.payload["intel"]
    assert p.payload["intel"]["key_pass"]["distance_m"] == 38.5


def test_producer_intel_is_dropped_when_the_moment_has_none():
    m = _moment(kind=MomentKind.CARD, player=None, state=_state(players={}))
    model_made = OverlayProposal(proposal_id="p-1", match_id="m", moment_id="mo-1", layer=OverlayLayer.LOWER_THIRD,
                                 line="x", reasoning="r", payload={"intel": {"shot_speed_kmh": 150}})
    assert "intel" not in with_intel(model_made, m).payload


# ---------- variants ----------

def test_analyst_fallback_quotes_the_intel_on_a_pass_moment():
    m = _moment(metrics=_engine_metrics())
    by_persona = {v.persona: v.text for v in fallback_variants(m, "Arden splits the line",
                                                               [(p, "none", "en", {}) for p in Persona])}
    assert by_persona[Persona.ANALYST] == "Arden splits the line (pass 38.5 m, difficulty 0.82)"
    assert by_persona[Persona.NEWCOMER] == "Arden splits the line"


def test_analyst_fallback_keeps_xg_on_a_big_chance():
    m = _moment(kind=MomentKind.BIG_CHANCE, metrics=MomentMetrics(shot_speed_kmh=104.2))
    analyst = fallback_variants(m, "Big chance", [(Persona.ANALYST, "none", "en", {})])[0].text
    assert analyst.startswith("Big chance (xG")


# ---------- the agents receive it ----------

class _RecordingAgent:
    name = "recording"

    def __init__(self, reply: str) -> None:
        self.reply, self.inputs = reply, []

    async def run(self, text: str):
        self.inputs.append(json.loads(text))
        return type("R", (), {"text": self.reply})()


def test_every_agent_receives_the_intel_block():
    m = _moment(metrics=_engine_metrics())
    pipeline = MomentPipeline()
    pipeline.explainer = _RecordingAgent(_expl(m).model_dump_json())
    pipeline.narrator = _RecordingAgent("Arden splits the line")
    pipeline.personalizer = _RecordingAgent("[]")
    pipeline.localizer = _RecordingAgent("[]")
    p = fallback_proposal(m, _expl(m), "x")
    pipeline.producer = _RecordingAgent(ProducerDecision(
        propose=True, layer=p.layer, t_start_ms=p.t_start_ms, t_end_ms=p.t_end_ms, line=p.line,
        payload_json=json.dumps(p.payload), reasoning=p.reasoning, alternatives=[]).model_dump_json())
    asyncio.run(pipeline.process(m))
    for agent in (pipeline.explainer, pipeline.narrator, pipeline.personalizer, pipeline.localizer,
                  pipeline.producer):
        intel = agent.inputs[0]["intel"]
        assert intel["metrics"]["key_pass"]["difficulty"] == 0.82
        assert any("38.5 m" in f for f in intel["facts"])
        assert intel["team_pass_accuracy_pct"] == {"har": 85.0, "nor": None}


def test_derived_speed_threshold_uses_the_engines_rule_and_is_not_repeated():
    # Stats engine raised the moment but sent no metrics or indicator (today's state of ingest).
    m = _moment(kind=MomentKind.SPEED_THRESHOLD, importance=0.35, summary="Ade Pike hits 33.1 km/h")
    got = intel_for(m)
    assert got is not None and got.thresholds[0].threshold == 32 and got.thresholds[0].value == 33.1
    assert got.player_distance_km == 6.24 and got.player_sprints == 11
    facts = intel_facts(got, lambda pid: NAMES.get(pid or "", ""))
    assert facts[0] == "Ade Pike: top speed 33.1 km/h (threshold 32 km/h)"
    analyst = fallback_variants(m, "Ade Pike hits 33.1 km/h", [(Persona.ANALYST, "none", "en", {})])[0].text
    assert analyst == "Ade Pike hits 33.1 km/h"


def test_derived_path_adds_no_running_totals_to_a_card():
    assert intel_for(_moment(kind=MomentKind.CARD)) is None


def test_the_result_and_the_graphic_carry_display_names_for_the_viewer():
    from simulator.cli import build_meta

    meta = build_meta(42)
    pid = meta.home.players[8].player_id
    metrics = MomentMetrics(player=pid, player_speed_kmh=33.1)
    res = asyncio.run(MomentPipeline().process(_moment(kind=MomentKind.SPEED_THRESHOLD, metrics=metrics, player=pid,
                                                       importance=0.35), meta=meta))
    assert res.intel is not None and res.intel["names"] == {pid: meta.home.players[8].name}
    assert res.proposal is not None and res.proposal.payload["intel"]["names"] == res.intel["names"]


def test_analyst_text_does_not_repeat_a_speed_written_without_decimals():
    m = _moment(kind=MomentKind.SPEED_THRESHOLD, importance=0.35, summary="Ade Pike hits 32 km/h")
    m.state.thresholds = [ThresholdIndicator(kind="top_speed", player="har-09", event_id=m.event_ids[0],
                                             value=32.0, threshold=32, unit="km/h")]
    analyst = fallback_variants(m, "Ade Pike hits 32 km/h", [(Persona.ANALYST, "none", "en", {})])[0].text
    assert analyst == "Ade Pike hits 32 km/h"


def test_allow_list_keeps_the_rating_and_its_percent_form_only():
    from agents.match_intel import intel_numbers
    kp = PassQuality(event_id="e", team="har", player="har-08", distance_m=38.5, difficulty=0.82)
    nums = intel_numbers(MomentMetrics(key_pass=kp))
    assert 0.82 in nums and 82 in nums and 8 not in nums
