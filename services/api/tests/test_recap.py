from api.main import app, hub
from api_factories import match_state
from crq_schemas import RecapPoint, TeamStats
from fastapi.testclient import TestClient

MIN = 60_000


def _point(play_ms: int, summary: str) -> RecapPoint:
    return RecapPoint(play_ms=play_ms, period=1, t_ms=play_ms, kind="big_chance", importance=0.7, summary=summary,
                      event_ids=[f"e-{play_ms}"])


def _live_match(now_play_ms: int, points: list[RecapPoint]) -> None:
    hub.match_state = match_state(home=TeamStats(team="har", goals=2), away=TeamStats(team="nor", goals=1),
                                  recap_points=points)
    hub.clock.play_ms = now_play_ms


def test_recap_returns_points_inside_the_window_only():
    _live_match(40 * MIN, [_point(5 * MIN, "too old"), _point(31 * MIN, "in window"), _point(40 * MIN, "just now")])
    body = TestClient(app).get("/recap", params={"minutes": 10}).json()
    assert [p["summary"] for p in body["points"]] == ["in window", "just now"]
    assert (body["from_play_ms"], body["to_play_ms"]) == (30 * MIN, 40 * MIN)


def test_recap_reports_score_and_leaves_generated_text_empty():
    _live_match(12 * MIN, [])
    body = TestClient(app).get("/recap", params={"minutes": 20}).json()
    assert body["score"] == "2-1" and body["text"] == "" and body["meta"]["routing"] == "template"
    assert body["from_play_ms"] == 0


def test_recap_rejects_windows_other_than_10_20_30():
    _live_match(12 * MIN, [])
    assert TestClient(app).get("/recap", params={"minutes": 15}).status_code == 422


def test_recap_before_kickoff_is_not_found():
    assert TestClient(app).get("/recap").status_code == 404


def test_a_new_match_does_not_recap_the_last_one_while_it_loads():
    from simulator.cli import build_meta

    _live_match(40 * MIN, [_point(35 * MIN, "last match")])
    hub.new_match(build_meta(5))  # the new folder is still loading (built in a worker thread)
    assert TestClient(app).get("/recap").status_code == 404
