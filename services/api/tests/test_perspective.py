"""Allegiance framing is code: deterministic, per viewer, and never touches the approved line."""

import pytest
from api.main import ViewerPrefs, app, hub
from api.perspective import perspective, score_text
from api_factories import RecordingSocket, match_state, proposal
from crq_schemas import OverlayPacket, TeamStats
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from simulator.cli import build_meta


def _score(home: int, away: int):
    return match_state(home=TeamStats(team="har", goals=home), away=TeamStats(team="nor", goals=away))


@pytest.mark.parametrize(("lang", "ours", "theirs", "expected"), [
    ("en", 2, 1, "2–1 up"), ("en", 0, 1, "0–1 down"), ("en", 1, 1, "level at 1–1"),
    ("es", 2, 1, "ganando 2–1"), ("es", 0, 1, "perdiendo 0–1"), ("es", 1, 1, "empate a 1–1"),
    ("hi", 2, 1, "2–1 से आगे"), ("hi", 0, 1, "0–1 से पीछे"), ("hi", 1, 1, "1–1 की बराबरी"),
])
def test_score_text_reads_from_the_viewers_side_in_their_language(lang, ours, theirs, expected):
    assert score_text(ours, theirs, lang) == expected


def test_perspective_for_away_supporter_puts_their_team_first():
    framing = perspective(_score(2, 1), ViewerPrefs(allegiance="away"), meta=None)
    assert framing == {"side": "away", "team": "nor", "color": None, "score": [1, 2], "score_text": "1–2 down"}


def test_perspective_uses_the_team_colour_from_match_meta():
    meta = build_meta(42)
    state = match_state(home=TeamStats(team=meta.home.team_id), away=TeamStats(team=meta.away.team_id))
    assert perspective(state, ViewerPrefs(allegiance="home"), meta)["color"] == meta.home.primary_color


def test_neutral_viewer_gets_no_perspective():
    assert perspective(_score(2, 1), ViewerPrefs(), meta=None) is None


def _aired_by(allegiance: str) -> OverlayPacket:
    ws = RecordingSocket()
    hub.viewers[ws] = ViewerPrefs(allegiance=allegiance)
    hub.match_state = _score(1, 0)
    p = proposal()
    hub.proposals[p.proposal_id] = p
    hub.results[p.moment_id] = {"variants": []}
    TestClient(app).post(f"/proposals/{p.proposal_id}/approve")
    return OverlayPacket.model_validate(ws.of_type("overlay")[0]["item"])


def test_supporter_packet_is_framed_without_changing_the_approved_line():
    packet = _aired_by("away")
    assert packet.allegiance == "away" and packet.payload["perspective"]["score_text"] == "0–1 down"
    assert packet.line == "A line"


def test_neutral_packet_and_the_canonical_feed_packet_stay_unframed():
    packet = _aired_by("neutral")
    assert packet.allegiance == "neutral" and "perspective" not in packet.payload
    assert "perspective" not in hub.feed.log[0]["item"]["payload"]


def test_viewer_socket_accepts_allegiance_and_refuses_unknown_sides():
    client = TestClient(app)
    with client.websocket_connect("/ws/viewer?allegiance=away"):
        assert list(hub.viewers.values())[0].allegiance == "away"
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/viewer?allegiance=both"):
        pass
