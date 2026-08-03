"""Open-Meteo client and the derived snow metrics the report needs.

Open-Meteo is free, needs no API key, and accepts an ``elevation`` parameter that
downscales the model to a given height - so base and summit conditions come from
two calls to the same endpoint.

Notes on the API, verified against a live response rather than the docs:

* ``snow_depth`` follows ``precipitation_unit``. Requesting inches yields **feet**,
  not the metres the docs imply, so the unit is read back off the response.
* ``past_days=3`` prepends three days to *both* the hourly and daily arrays, so the
  7-day forecast has to be sliced from today rather than taken from the front.
* With ``timezone=auto`` every timestamp is naive resort-local time, so "now" must
  be derived from ``utc_offset_seconds`` and not from the server's clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests

from . import wmo
from .cache import TTLCache
from .mountains import Mountain

API_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 10
FORECAST_DAYS = 7
PAST_DAYS = 3

# Imperial throughout; change these three to switch the whole app to metric.
TEMPERATURE_UNIT = "fahrenheit"
WIND_SPEED_UNIT = "mph"
PRECIPITATION_UNIT = "inch"

_INCHES_PER_FOOT = 12.0
_INCHES_PER_METRE = 39.3701
_INCHES_PER_CM = 0.393701

_payload_cache: TTLCache[dict] = TTLCache()


class WeatherUnavailable(RuntimeError):
    """The upstream forecast could not be retrieved."""


@dataclass(frozen=True)
class Conditions:
    """Current conditions at one elevation."""

    elevation_m: int
    temperature_f: float | None
    feels_like_f: float | None
    wind_mph: float | None
    gust_mph: float | None
    weather_code: int | None

    @property
    def weather_label(self) -> str:
        return wmo.label(self.weather_code)

    @property
    def weather_icon(self) -> str:
        return wmo.icon(self.weather_code)

    @property
    def is_snowing(self) -> bool:
        return wmo.is_snowing(self.weather_code)


@dataclass(frozen=True)
class ElevationReport:
    """Everything measured at a single elevation."""

    label: str
    conditions: Conditions
    new_snow_24h_in: float
    new_snow_48h_in: float
    new_snow_72h_in: float
    snow_depth_in: float | None


@dataclass(frozen=True)
class DayForecast:
    day: date
    weather_code: int | None
    high_f: float | None
    low_f: float | None
    snowfall_in: float | None
    summit_snowfall_in: float | None
    wind_max_mph: float | None

    @property
    def weather_label(self) -> str:
        return wmo.label(self.weather_code)

    @property
    def weather_icon(self) -> str:
        return wmo.icon(self.weather_code)

    @property
    def day_label(self) -> str:
        return self.day.strftime("%a")

    @property
    def date_label(self) -> str:
        # %-d is glibc-only, so strip the zero padding by hand for Windows.
        return f"{self.day.strftime('%b')} {self.day.day}"


@dataclass(frozen=True)
class MountainReport:
    mountain: Mountain
    base: ElevationReport
    summit: ElevationReport
    forecast: list[DayForecast] = field(default_factory=list)
    observed_at: datetime | None = None
    timezone_name: str = ""
    stale: bool = False

    @property
    def headline_new_snow_in(self) -> float:
        """Summit 24h total - the number skiers actually care about."""
        return self.summit.new_snow_24h_in


def _fetch_payload(mountain: Mountain, elevation_m: int) -> dict:
    params = {
        "latitude": mountain.lat,
        "longitude": mountain.lon,
        "elevation": elevation_m,
        "current": (
            "temperature_2m,apparent_temperature,wind_speed_10m,"
            "wind_gusts_10m,weather_code,snowfall"
        ),
        "hourly": "snowfall,snow_depth,temperature_2m",
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "snowfall_sum,wind_speed_10m_max"
        ),
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "temperature_unit": TEMPERATURE_UNIT,
        "wind_speed_unit": WIND_SPEED_UNIT,
        "precipitation_unit": PRECIPITATION_UNIT,
        "timezone": "auto",
    }
    try:
        response = requests.get(API_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise WeatherUnavailable(
            f"could not fetch weather for {mountain.name}: {exc}"
        ) from exc


def _payload(mountain: Mountain, elevation_m: int, *, allow_stale: bool = True) -> dict:
    key = (mountain.id, elevation_m)
    cached = _payload_cache.get(key)
    if cached is not None:
        return cached

    try:
        payload = _fetch_payload(mountain, elevation_m)
    except WeatherUnavailable:
        stale = _payload_cache.get_entry(key) if allow_stale else None
        if stale is None:
            raise
        marked = dict(stale.value)
        marked["_stale"] = True
        return marked

    _payload_cache.set(key, payload)
    return payload


def local_now(payload: dict) -> datetime:
    """Current time at the resort, naive, matching the API's timestamps."""
    offset = int(payload.get("utc_offset_seconds", 0))
    return (datetime.now(timezone.utc) + timedelta(seconds=offset)).replace(tzinfo=None)


def _parse_times(values: list[str]) -> list[datetime]:
    return [datetime.fromisoformat(value) for value in values]


def _to_inches(value: float, unit: str) -> float:
    """Normalise a depth in whatever unit Open-Meteo returned into inches."""
    unit = (unit or "").strip().lower()
    if unit in {"ft", "feet"}:
        return value * _INCHES_PER_FOOT
    if unit in {"m", "metre", "meter"}:
        return value * _INCHES_PER_METRE
    if unit == "cm":
        return value * _INCHES_PER_CM
    return value  # already inches


def snowfall_window(payload: dict, hours: int, now: datetime | None = None) -> float:
    """Total snowfall over the ``hours`` ending now, in inches.

    Only possible because ``past_days`` backfills the hourly series.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    amounts = hourly.get("snowfall") or []
    if not times or not amounts:
        return 0.0

    reference = now if now is not None else local_now(payload)
    start = reference - timedelta(hours=hours)

    total = 0.0
    for stamp, amount in zip(_parse_times(times), amounts):
        if amount is None:
            continue
        if start < stamp <= reference:
            total += float(amount)
    return round(total, 1)


def current_snow_depth(payload: dict, now: datetime | None = None) -> float | None:
    """Most recent snow depth at or before now, in inches."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    depths = hourly.get("snow_depth") or []
    if not times or not depths:
        return None

    unit = (payload.get("hourly_units") or {}).get("snow_depth", "")
    reference = now if now is not None else local_now(payload)

    latest: float | None = None
    for stamp, depth in zip(_parse_times(times), depths):
        if stamp > reference:
            break
        if depth is not None:
            latest = float(depth)

    if latest is None:
        return None
    return round(_to_inches(latest, unit), 1)


def _conditions(payload: dict, elevation_m: int) -> Conditions:
    current = payload.get("current") or {}
    return Conditions(
        elevation_m=elevation_m,
        temperature_f=current.get("temperature_2m"),
        feels_like_f=current.get("apparent_temperature"),
        wind_mph=current.get("wind_speed_10m"),
        gust_mph=current.get("wind_gusts_10m"),
        weather_code=current.get("weather_code"),
    )


def _elevation_report(
    payload: dict, label: str, elevation_m: int, now: datetime
) -> ElevationReport:
    return ElevationReport(
        label=label,
        conditions=_conditions(payload, elevation_m),
        new_snow_24h_in=snowfall_window(payload, 24, now),
        new_snow_48h_in=snowfall_window(payload, 48, now),
        new_snow_72h_in=snowfall_window(payload, 72, now),
        snow_depth_in=current_snow_depth(payload, now),
    )


def _build_forecast(
    base_payload: dict, summit_payload: dict, now: datetime
) -> list[DayForecast]:
    """Seven days from today, temperatures at base and snowfall at summit."""
    daily = base_payload.get("daily") or {}
    days = daily.get("time") or []
    if not days:
        return []

    summit_daily = summit_payload.get("daily") or {}
    summit_snow = dict(
        zip(summit_daily.get("time") or [], summit_daily.get("snowfall_sum") or [])
    )

    def column(name: str) -> list:
        values = daily.get(name) or []
        return list(values) + [None] * (len(days) - len(values))

    codes = column("weather_code")
    highs = column("temperature_2m_max")
    lows = column("temperature_2m_min")
    snow = column("snowfall_sum")
    winds = column("wind_speed_10m_max")

    today = now.date()
    forecast: list[DayForecast] = []
    for index, day_str in enumerate(days):
        day = date.fromisoformat(day_str)
        if day < today:  # drop the past_days padding
            continue
        forecast.append(
            DayForecast(
                day=day,
                weather_code=codes[index],
                high_f=highs[index],
                low_f=lows[index],
                snowfall_in=snow[index],
                summit_snowfall_in=summit_snow.get(day_str),
                wind_max_mph=winds[index],
            )
        )
        if len(forecast) == FORECAST_DAYS:
            break
    return forecast


def get_report(mountain: Mountain) -> MountainReport:
    """Fetch (or serve from cache) a full report for one mountain.

    Raises :class:`WeatherUnavailable` when the data cannot be retrieved and no
    cached copy exists to fall back on.
    """
    base_payload = _payload(mountain, mountain.base_elevation_m)
    summit_payload = _payload(mountain, mountain.summit_elevation_m)

    now = local_now(base_payload)
    stale = bool(base_payload.get("_stale") or summit_payload.get("_stale"))

    return MountainReport(
        mountain=mountain,
        base=_elevation_report(base_payload, "Base", mountain.base_elevation_m, now),
        summit=_elevation_report(
            summit_payload, "Summit", mountain.summit_elevation_m, now
        ),
        forecast=_build_forecast(base_payload, summit_payload, now),
        observed_at=now,
        timezone_name=base_payload.get("timezone", ""),
        stale=stale,
    )


def report_to_dict(report: MountainReport) -> dict:
    """JSON-serialisable view of a report, for the API route."""

    def elevation(item: ElevationReport) -> dict:
        conditions = item.conditions
        return {
            "label": item.label,
            "elevation_m": conditions.elevation_m,
            "temperature_f": conditions.temperature_f,
            "feels_like_f": conditions.feels_like_f,
            "wind_mph": conditions.wind_mph,
            "gust_mph": conditions.gust_mph,
            "weather_code": conditions.weather_code,
            "weather_label": conditions.weather_label,
            "new_snow_in": {
                "24h": item.new_snow_24h_in,
                "48h": item.new_snow_48h_in,
                "72h": item.new_snow_72h_in,
            },
            "snow_depth_in": item.snow_depth_in,
        }

    return {
        "mountain": {
            "id": report.mountain.id,
            "name": report.mountain.name,
            "region": report.mountain.region,
            "state": report.mountain.state,
            "country": report.mountain.country,
            "lat": report.mountain.lat,
            "lon": report.mountain.lon,
            "base_elevation_ft": report.mountain.base_elevation_ft,
            "summit_elevation_ft": report.mountain.summit_elevation_ft,
            "website": report.mountain.website,
        },
        "base": elevation(report.base),
        "summit": elevation(report.summit),
        "forecast": [
            {
                "date": day.day.isoformat(),
                "weather_code": day.weather_code,
                "weather_label": day.weather_label,
                "high_f": day.high_f,
                "low_f": day.low_f,
                "snowfall_in": day.snowfall_in,
                "summit_snowfall_in": day.summit_snowfall_in,
                "wind_max_mph": day.wind_max_mph,
            }
            for day in report.forecast
        ],
        "observed_at": report.observed_at.isoformat() if report.observed_at else None,
        "timezone": report.timezone_name,
        "stale": report.stale,
        "source": "Open-Meteo",
    }
