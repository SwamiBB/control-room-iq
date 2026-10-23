"""Done-criterion: a CRQ_OFFLINE=1 replay produces each demo moment at its scripted minute."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402
from api.offline import check_demo_moments, replay_offline  # noqa: E402
from crq_schemas import MomentKind  # noqa: E402
from simulator.cli import reference_paths  # noqa: E402
from simulator.scripted import DATA_DIR  # noqa: E402

STORIES = sorted(DATA_DIR.glob("storyline*.json"))


@pytest.fixture(scope="module", params=STORIES, ids=lambda p: p.stem)
def run(request):
    story = json.loads(request.param.read_text(encoding="utf-8"))
    return story, asyncio.run(replay_offline(reference_paths(request.param)[0]))


def test_every_demo_moment_appears_at_its_minute(run):
    story, rows = run
    assert check_demo_moments(story, rows) == []
    assert not [f for r in rows for f in r.failures]


def test_goals_go_full_screen_and_plain_stoppages_stay_off_the_queue(run):
    _, rows = run
    assert all(r.proposal and r.proposal.layer.value == "full_screen" for r in rows if r.moment.kind == MomentKind.GOAL)
    plain = [r for r in rows if r.moment.kind == MomentKind.STOPPAGE and r.moment.importance < 0.35]
    assert plain and not any(r.proposal for r in plain), "ordinary fouls reach the fan, not the operator"
