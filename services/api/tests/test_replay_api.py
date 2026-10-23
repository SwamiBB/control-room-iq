import os
import time

os.environ["CRQ_OFFLINE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402


def test_replay_controls():
    with TestClient(api.app) as c:
        assert c.get("/api/replay/status").status_code in (200, 409)
        assert c.get("/api/replay", params={"seed": 999}).status_code == 404

        r = c.get("/api/replay", params={"seed": 42, "speed": 1})
        assert r.status_code == 200 and r.json()["state"] == "playing"

        r = c.post("/api/replay/jump", params={"minute": 41, "second": 12})
        assert r.json()["clock"] == {"period": 1, "minute": 41, "second": 12}
        assert api.hub.state["minute"] in (40, 41), "state was folded up to the jump target"

        assert c.post("/api/replay/pause").json()["state"] == "paused"
        assert c.post("/api/replay/resume").json()["state"] == "playing"
        assert c.post("/api/replay/speed", params={"x": 0}).status_code == 422
        assert c.post("/api/replay/speed", params={"x": 4}).json()["speed"] == 4

        r = c.post("/api/replay/jump", params={"minute": 78})
        assert r.json()["clock"]["period"] == 2 and r.json()["clock"]["minute"] == 78
        api.replay_session.task.cancel()


def test_hero_scene_is_scheduled_with_the_goal_on_full_screen():
    with TestClient(api.app) as c:
        c.get("/api/replay", params={"seed": 42, "speed": 1})
        c.post("/api/replay/jump", params={"minute": 41, "second": 12})
        c.post("/api/replay/speed", params={"x": 8})
        deadline = time.monotonic() + 10
        goal = None
        while time.monotonic() < deadline and goal is None:
            time.sleep(0.1)
            goal = next((p for p in api.hub.proposals.values() if p.line.startswith("GOAL Finn Oakes")), None)
        assert goal is not None and goal.layer.value == "full_screen" and goal.window_id
        screen = c.get("/api/screen").json()
        assert goal.proposal_id in {i["proposal_id"] for i in screen["queued"] + screen["on_air"]}
        api.replay_session.task.cancel()


def test_strike_cue_reaches_the_viewer_within_one_second():
    with TestClient(api.app) as c, c.websocket_connect("/ws/viewer?persona=accessibility&lang=en") as viewer:
        c.get("/api/replay", params={"seed": 42, "speed": 1})
        c.post("/api/replay/pause")
        t0 = time.monotonic()
        c.post("/api/replay/jump", params={"minute": 41, "second": 12})  # lands on the hero strike
        c.post("/api/replay/resume")
        msg = viewer.receive_json()
        elapsed = time.monotonic() - t0
        assert msg["type"] == "cue"
        cue = msg["cue"]
        assert (cue["team"], cue["direction"], cue["clock"]) == ("har", "center",
                                                                 {"period": 1, "minute": 41, "second": 12})
        assert elapsed < 1.0, f"cue took {elapsed:.2f} s"
        api.replay_session.task.cancel()
