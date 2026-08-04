# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

The venv lives at `.venv`. PowerShell execution policy on this machine blocks
`Activate.ps1`, so call the venv interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m flask --app app run --debug   # dev server on :5000
.\.venv\Scripts\python.exe -m pytest                        # full suite (~0.2s)
.\.venv\Scripts\python.exe -m pytest tests/test_weather.py  # one file
.\.venv\Scripts\python.exe -m pytest -k snowfall_window     # one test by name
```

There is no linter, formatter, or build step configured.

## Architecture

Three layers, each testable without the ones above it:

- `skireport/mountains.py` — the resort registry. Knows nothing about weather.
- `skireport/weather.py` — Open-Meteo client and all derived snow metrics. Knows
  nothing about HTTP routing.
- `app.py` — Flask routes. Knows nothing about how snow totals are computed.

Routes call exactly one function, `weather.get_report(mountain)`, which returns a
`MountainReport` of frozen dataclasses. Templates never touch raw JSON; if a
template needs a new value, add it to a dataclass rather than passing the payload
through.

Resorts live in `data/mountains.json`, not in Python. Adding one is a data edit.
The registry is validated on load (`_build` in `mountains.py`) — required keys,
slug-shaped unique ids, coordinate ranges, summit above base — so a malformed
entry fails loudly at startup instead of rendering a broken page. Adding a *field*
to the dataclass makes it required on every entry; the suite will catch a partial
rollout immediately.

Base and summit are two separate calls to the same endpoint with different
`elevation` values. Both payloads are already in hand by the time the forecast is
built, which is why `_build_forecast` can take temperatures from the base payload
and snowfall from the summit payload at no extra cost.

## Open-Meteo behaviour that contradicts its docs

All of these were verified against live responses. Each would cause silently wrong
numbers rather than a crash, so do not "simplify" the code that handles them:

- **`snow_depth` follows `precipitation_unit`.** Requesting inches yields **feet**,
  not the metres the docs imply. `_to_inches` reads the unit off `hourly_units`
  rather than assuming — keep it that way.
- **`past_days=3` pads both the hourly and daily arrays.** `daily` arrives with 10
  rows, three of them history. `_build_forecast` drops anything before today;
  taking the first 7 would render last week as a forecast.
- **`timezone=auto` returns naive resort-local timestamps.** "Now" must come from
  `local_now()` (UTC plus `utc_offset_seconds`), never from the server clock, or
  every trailing-snow window is skewed by the timezone difference.
- **`past_days` caps at 93**, so the forecast API cannot cover a full ski season.

### The archive API is not a drop-in for season totals

`archive-api.open-meteo.com` accepts `elevation` and echoes it back, but **ignores
it** — identical snowfall totals with and without it. It is ERA5 on a ~25 km grid
and under-reports mountain snowfall by roughly 5× (68.7" for Jan–Mar 2026 at Alta,
against a real ~545"/season average). Do not build season-to-date totals on it; the
output looks authoritative and is wrong.

## Caching

`skireport/cache.py` is a 15-minute TTL cache keyed by `(mountain_id, elevation)`.
The non-obvious part: **expired entries are never evicted, only hidden from
`get()`**. `get_entry()` returns them regardless of age, which is what lets
`_payload` fall back to a stale copy when a fetch fails, tagging it `_stale` so the
page shows a banner instead of an error. `get()` answers "is there a usable value?";
`get_entry()` answers "is there any value?". Preserve that split.

## Tests

The suite never touches the network. `tests/conftest.py` monkeypatches
`_fetch_payload` and freezes `local_now` to `FIXTURE_NOW` (2025-01-15T12:00).

`tests/fixtures/open_meteo_sample.json` is a real response with a synthetic time
axis: 1.0"/h for the last 24h, 0.5"/h for 24–48h, 0.25"/h for 48–72h. That makes the
trailing windows exactly assertable at **24.0 / 36.0 / 42.0"** — change the fixture
and those expectations move with it.

When asserting on rendered HTML, remember Jinja escapes output: region names contain
`&` (`&amp;`) and the inch mark renders as `&#34;`.

Northern-hemisphere resorts read zero snow outside winter, which is correct, not a
bug. To exercise the snow path against live data off-season, point the client at
southern-hemisphere coordinates (Portillo, Valle Nevado, Treble Cone) — see the
invariant that 24h ≤ 48h ≤ 72h totals must nest.

## Conventions

- Units are imperial for display, metric in storage. `TEMPERATURE_UNIT`,
  `WIND_SPEED_UNIT` and `PRECIPITATION_UNIT` at the top of `weather.py` switch the
  whole app; unit strings are read back off the response so conversions follow.
- Missing data returns `None`, never `0.0` — the `val()` macro renders `—`, so the
  page never claims zero snow when it simply has no reading.
- `mountains.get()` returns `None` for unknown ids; routes decide to `abort(404)`.
- Hand-written CSS in `static/style.css`, no framework and no build step. Palette
  is the `:root` custom properties.
