"""WMO weather interpretation codes -> short label and emoji icon.

Open-Meteo reports conditions as WMO code 4677 values. Codes are grouped rather
than listed exhaustively; anything unrecognised falls back to a neutral label.
"""

_CODES: dict[int, tuple[str, str]] = {
    0: ("Clear", "☀️"),
    1: ("Mostly clear", "\U0001f324️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"),
    45: ("Fog", "\U0001f32b️"),
    48: ("Freezing fog", "\U0001f32b️"),
    51: ("Light drizzle", "\U0001f327️"),
    53: ("Drizzle", "\U0001f327️"),
    55: ("Heavy drizzle", "\U0001f327️"),
    56: ("Freezing drizzle", "\U0001f9ca"),
    57: ("Freezing drizzle", "\U0001f9ca"),
    61: ("Light rain", "\U0001f327️"),
    63: ("Rain", "\U0001f327️"),
    65: ("Heavy rain", "\U0001f327️"),
    66: ("Freezing rain", "\U0001f9ca"),
    67: ("Freezing rain", "\U0001f9ca"),
    71: ("Light snow", "\U0001f328️"),
    73: ("Snow", "❄️"),
    75: ("Heavy snow", "\U0001f3bf"),
    77: ("Snow grains", "\U0001f328️"),
    80: ("Light showers", "\U0001f326️"),
    81: ("Showers", "\U0001f327️"),
    82: ("Heavy showers", "⛈️"),
    85: ("Snow showers", "\U0001f328️"),
    86: ("Heavy snow showers", "\U0001f3bf"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm, hail", "⛈️"),
    99: ("Thunderstorm, hail", "⛈️"),
}

_UNKNOWN = ("Unknown", "❓")

# Codes at or above this value involve frozen precipitation reaching the ground.
_SNOW_CODES = frozenset({71, 73, 75, 77, 85, 86})


def describe(code: int | None) -> tuple[str, str]:
    """Return ``(label, icon)`` for a WMO weather code."""
    if code is None:
        return _UNKNOWN
    return _CODES.get(int(code), _UNKNOWN)


def label(code: int | None) -> str:
    return describe(code)[0]


def icon(code: int | None) -> str:
    return describe(code)[1]


def is_snowing(code: int | None) -> bool:
    """True when the code represents snow falling."""
    return code is not None and int(code) in _SNOW_CODES
