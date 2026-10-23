"""Every fixture validates against its model. Fixtures are the contract until live wiring."""

import json
from pathlib import Path

import pytest
from crq_schemas import (Decision, EvaluationRecord, FanCard, MatchState, Moment, OverlayProposal, ScreenState,
                         StrikeCue, Team)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DATA = Path(__file__).resolve().parents[3] / "data"

CASES = [
    ("match_state.json", MatchState),
    ("moment_big_chance_strike.json", Moment),
    ("moment_big_chance_result.json", Moment),
    ("moment_goal.json", Moment),
    ("moment_stoppage_card.json", Moment),
    ("strike_cue.json", StrikeCue),
    ("overlay_proposal.json", OverlayProposal),
    ("screen_state.json", ScreenState),
    ("decision.json", Decision),
    ("evaluation_record.json", EvaluationRecord),
]


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,model", CASES)
def test_fixture_validates(name, model):
    model.model_validate(_load(name))


def test_fan_cards_cover_three_languages():
    cards = [FanCard.model_validate(c) for c in _load("fan_card.json")]
    assert sorted(c.lang for c in cards) == ["en", "es", "hi"]
    assert all(c.released_by for c in cards), "nothing reaches the fan without a decision"


def test_every_fixture_file_is_covered():
    covered = {name for name, _ in CASES} | {"fan_card.json"}
    assert {p.name for p in FIXTURES.glob("*.json")} == covered


def test_moment_cites_resolve_inside_snapshot():
    for name in ("moment_big_chance_result.json", "moment_goal.json", "moment_stoppage_card.json"):
        m = Moment.model_validate(_load(name))
        assert m.trigger_event_id in json.dumps(m.snapshot), name


def test_clubs_are_valid_teams():
    clubs = json.loads((DATA / "clubs.json").read_text(encoding="utf-8"))["clubs"]
    teams = [Team.model_validate(c) for c in clubs]
    assert [t.team_id for t in teams] == ["har", "nfu", "rva", "irb"]
    for t in teams:
        assert len(t.players) == 16
        assert sum(p.position == "GK" for p in t.players) == 2
        assert len({p.player_id for p in t.players}) == 16
