"""replay --eventhub: what reaches Event Hubs, with a fake producer (#11, #12)."""

import json
from pathlib import Path

import azure.eventhub.aio
import azure.identity.aio
from simulator import cli


class FakeProducer:
    sent: list[tuple[str | None, list[dict]]] = []

    def __init__(self, **_):
        FakeProducer.sent = []

    async def send_batch(self, batch, partition_key=None):
        self.sent.append((partition_key, [json.loads(e.body_as_str()) for e in batch]))

    async def close(self):
        pass


def _match(tmp_path: Path) -> Path:
    meta = cli.build_meta(5)
    events = list(cli.MatchEngine(meta).run())[:30]  # ends mid-batch, so the final flush sends something
    path = tmp_path / "m.jsonl"
    cli.write_match(path, meta, events)
    return path


def test_replay_sends_the_match_meta_first_and_every_batch_on_the_match_partition(tmp_path, monkeypatch):
    monkeypatch.setattr(azure.eventhub.aio, "EventHubProducerClient", FakeProducer)
    monkeypatch.setattr(azure.identity.aio, "DefaultAzureCredential", lambda: None)
    monkeypatch.setenv("EVENTHUB_NAMESPACE", "fake.servicebus.windows.net")
    path = _match(tmp_path)
    cli.main(["replay", str(path), "--speed", "1e9", "--eventhub"])

    sent = FakeProducer.sent
    match_id = json.loads(path.read_text(encoding="utf-8").splitlines()[0])["match_id"]
    assert "home" in sent[0][1][0] and len(sent[0][1]) == 1, "the MatchMeta record goes first, on its own"
    assert {key for key, _ in sent} == {match_id}, "the final flush too"
    assert sum(len(b) for _, b in sent[1:]) == 30


def test_main_loads_dotenv_before_reading_settings(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "load_dotenv", lambda: calls.append("dotenv"))
    cli.main(["replay", str(_match(tmp_path)), "--speed", "1e9"])
    assert calls == ["dotenv"]
