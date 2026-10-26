"""The replay opens only match files under data/ (#22): no probing or echoing other files."""

from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_paths_outside_data_are_refused_before_any_file_is_touched():
    for file in ("/etc/passwd", "/proc/self/environ", "../pyproject.toml", "data/../pyproject.toml",
                 "data/reference/../../services/api/api/main.py", "data/reference/match-042.json"):
        r = client.post("/matches/replay", json={"file": file})
        assert r.status_code == 422, file
        assert "data/" in r.json()["detail"]


def test_a_missing_match_under_data_is_a_404():
    r = client.post("/matches/replay", json={"file": "data/reference/match-999.jsonl"})
    assert r.status_code == 404
