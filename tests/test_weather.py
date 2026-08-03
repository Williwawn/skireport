from datetime import datetime, timedelta

import pytest
import requests

from conftest import FIXTURE_NOW
from skireport import mountains, weather


# The fixture lays down 1.0"/h for the last 24h, 0.5"/h for 24-48h and
# 0.25"/h for 48-72h, so the trailing windows have known totals.
@pytest.mark.parametrize(
    "hours,expected",
    [(24, 24.0), (48, 36.0), (72, 42.0)],
)
def test_snowfall_windows(payload, hours, expected):
    assert weather.snowfall_window(payload, hours, FIXTURE_NOW) == expected


def test_snowfall_window_excludes_the_future(payload):
    """Hours after 'now' must never count toward new snow."""
    hourly = payload["hourly"]
    future = FIXTURE_NOW + timedelta(hours=5)
    index = hourly["time"].index(future.strftime("%Y-%m-%dT%H:%M"))
    hourly["snowfall"][index] = 99.0

    assert weather.snowfall_window(payload, 24, FIXTURE_NOW) == 24.0


def test_snowfall_window_tolerates_nulls(payload):
    payload["hourly"]["snowfall"][-30:] = [None] * 30
    assert weather.snowfall_window(payload, 24, FIXTURE_NOW) >= 0


def test_snow_depth_converts_feet_to_inches(payload):
    # Fixture reports 5.0 ft, which is what Open-Meteo returns for inch units.
    assert payload["hourly_units"]["snow_depth"] == "ft"
    assert weather.current_snow_depth(payload, FIXTURE_NOW) == 60.0


def test_snow_depth_handles_metres(payload):
    payload["hourly_units"]["snow_depth"] = "m"
    payload["hourly"]["snow_depth"] = [1.0] * len(payload["hourly"]["time"])
    assert weather.current_snow_depth(payload, FIXTURE_NOW) == pytest.approx(39.4, abs=0.1)


def test_snow_depth_missing_series(payload):
    payload["hourly"]["snow_depth"] = []
    assert weather.current_snow_depth(payload, FIXTURE_NOW) is None


def test_local_now_uses_the_resort_offset(payload):
    payload["utc_offset_seconds"] = -7 * 3600
    now = weather.local_now(payload)
    utc = datetime.utcnow()
    assert abs((utc - now).total_seconds() - 7 * 3600) < 60


def test_report_shape(offline):
    report = weather.get_report(mountains.get("jackson-hole"))

    assert report.base.label == "Base"
    assert report.summit.label == "Summit"
    assert report.summit.new_snow_24h_in == 24.0
    assert report.headline_new_snow_in == 24.0
    assert report.base.conditions.weather_label == "Heavy snow"
    assert report.base.conditions.is_snowing is True
    assert report.stale is False


def test_forecast_drops_past_days_and_caps_at_seven(offline):
    """past_days=3 pads the daily arrays; only today onward should survive."""
    report = weather.get_report(mountains.get("jackson-hole"))

    assert len(report.forecast) == 7
    assert report.forecast[0].day == FIXTURE_NOW.date()
    assert [d.day for d in report.forecast] == sorted(d.day for d in report.forecast)
    # Day 0 in the fixture is the 4th daily entry: 12.0" of snow.
    assert report.forecast[0].summit_snowfall_in == 12.0


def test_base_and_summit_are_fetched_separately(offline):
    jackson = mountains.get("jackson-hole")
    weather.get_report(jackson)

    assert offline == [
        ("jackson-hole", jackson.base_elevation_m),
        ("jackson-hole", jackson.summit_elevation_m),
    ]


def test_second_call_is_served_from_cache(offline):
    jackson = mountains.get("jackson-hole")
    weather.get_report(jackson)
    weather.get_report(jackson)

    assert len(offline) == 2  # not 4


def test_failure_without_cache_raises(monkeypatch):
    def boom(mountain, elevation_m):
        raise weather.WeatherUnavailable("nope")

    monkeypatch.setattr(weather, "_fetch_payload", boom)
    with pytest.raises(weather.WeatherUnavailable):
        weather.get_report(mountains.get("stowe"))


def test_failure_falls_back_to_stale_cache(offline, monkeypatch):
    jackson = mountains.get("jackson-hole")
    weather.get_report(jackson)  # warm the cache

    weather._payload_cache.ttl_seconds = 0  # force everything to look expired

    def boom(mountain, elevation_m):
        raise weather.WeatherUnavailable("upstream down")

    monkeypatch.setattr(weather, "_fetch_payload", boom)

    report = weather.get_report(jackson)
    assert report.stale is True
    assert report.summit.new_snow_24h_in == 24.0

    weather._payload_cache.ttl_seconds = 15 * 60


def test_network_errors_become_weather_unavailable(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(weather.requests, "get", boom)
    with pytest.raises(weather.WeatherUnavailable, match="could not fetch"):
        weather._fetch_payload(mountains.get("alta"), 2600)


def test_http_error_becomes_weather_unavailable(monkeypatch):
    class Response:
        def raise_for_status(self):
            raise requests.HTTPError("429 Too Many Requests")

    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: Response())
    with pytest.raises(weather.WeatherUnavailable):
        weather._fetch_payload(mountains.get("alta"), 2600)


def test_report_to_dict_is_json_ready(offline):
    import json

    report = weather.get_report(mountains.get("killington"))
    encoded = json.dumps(weather.report_to_dict(report))
    decoded = json.loads(encoded)

    assert decoded["mountain"]["id"] == "killington"
    assert decoded["summit"]["new_snow_in"]["24h"] == 24.0
    assert len(decoded["forecast"]) == 7
    assert decoded["source"] == "Open-Meteo"
