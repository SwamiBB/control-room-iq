"""Thursday done-criterion 4: CRQ_OFFLINE=1 replay produces each demo moment at its scripted minute."""

import os

os.environ["CRQ_OFFLINE"] = "1"

import asyncio  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402
from api.offline import check_demo_moments, replay_offline  # noqa: E402
from crq_schemas import MomentKind  # noqa: E402
from simulator.cli import reference_paths, write_match  # noqa: E402
from simulator.scripted import DATA_DIR, generate  # noqa: E402

STORIES = sorted(DATA_DIR.glob("storyline*.json"))


@pytest.fixture(scope="module", params=STORIES, ids=lambda p: p.stem)
def run(request, tmp_path_factory):
    meta, events = generate(request.param)  # regenerate rather than trust the checked-in file
    path = tmp_path_factory.mktemp("offline") / reference_paths(request.param)[0].name
    write_match(path, meta, events)
    story = json.loads(request.param.read_text(encoding="utf-8"))
    return story, asyncio.run(replay_offline(path))


def test_every_demo_moment_appears_at_its_minute(run):
    story, rows = run
    assert check_demo_moments(story, rows) == []
    assert not [f for r in rows for f in r.failures]


def test_goals_go_full_screen_and_plain_stoppages_stay_off_the_queue(run):
    _, rows = run
    assert all(r.proposal_layer == "full_screen" for r in rows if r.moment.kind == MomentKind.GOAL)
    plain = [r for r in rows if r.moment.kind == MomentKind.STOPPAGE and r.moment.importance < 0.35]
    assert plain and not any(r.proposal_layer for r in plain), "ordinary fouls reach the fan, not the operator"


def test_reference_match_file_is_current():
    """The checked-in reference match must equal what the seed generates (regenerate: simulator.cli reference)."""
    story = DATA_DIR / "storyline.json"
    meta, events = generate(story)
    lines = [meta.model_dump_json()] + [e.model_dump_json() for e in events]
    assert reference_paths(story)[0].read_text(encoding="utf-8").splitlines() == lines
