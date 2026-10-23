import os

os.environ["CRQ_OFFLINE"] = "1"

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from api.main import hub  # noqa: E402

FIXED_NOW = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fresh_hub():
    # The hub is module-global; reset it so every test runs in isolation and in any order.
    hub.reset()
    hub.now = lambda: FIXED_NOW
    yield hub
    hub.reset()
