import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURE = Path(__file__).parent / "fixtures" / "open_meteo_sample.json"

# The fixture's hourly/daily series are built around this instant.
FIXTURE_NOW = datetime(2025, 1, 15, 12, 0)


@pytest.fixture
def payload() -> dict:
    """A fresh copy of the sample Open-Meteo response."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def clear_weather_cache():
    from skireport import weather

    weather._payload_cache.clear()
    yield
    weather._payload_cache.clear()


@pytest.fixture
def offline(monkeypatch, payload):
    """Serve the fixture instead of hitting the network, and freeze 'now'."""
    from skireport import weather

    calls: list[tuple[str, int]] = []

    def fake_fetch(mountain, elevation_m):
        calls.append((mountain.id, elevation_m))
        return json.loads(json.dumps(payload))

    monkeypatch.setattr(weather, "_fetch_payload", fake_fetch)
    monkeypatch.setattr(weather, "local_now", lambda _payload: FIXTURE_NOW)
    return calls


@pytest.fixture
def client(offline):
    from app import create_app

    application = create_app()
    application.config.update(TESTING=True)
    with application.test_client() as test_client:
        yield test_client
