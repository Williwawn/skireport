# skiReport

A small Flask site that compiles weather for ski mountains. Pick a resort and get
current conditions at both base and summit, recent snowfall, and a seven-day outlook.

Weather comes from [Open-Meteo](https://open-meteo.com/) — free, no API key, no signup.

## Requirements

Python 3.10 or newer.

## Running it

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app run --debug
```

On macOS/Linux the activate line is `source .venv/bin/activate`.

Then open <http://127.0.0.1:5000/>.

## What it shows

For each mountain, at **base and summit elevation separately**:

- Current temperature, feels-like, wind and gusts, and sky conditions
- New snow over the trailing 24 / 48 / 72 hours
- Current snow depth
- A seven-day forecast — high/low, expected snowfall at the summit, max wind

Open-Meteo accepts an `elevation` parameter that downscales its model to a given
height, so the base and summit figures are genuinely different forecasts rather
than the same numbers repeated.

## Routes

| Route | Purpose |
| --- | --- |
| `/` | Mountain picker, grouped by region |
| `/mountain/<id>` | The weather report — a shareable, bookmarkable URL |
| `/api/mountains` | JSON list of every mountain |
| `/api/mountain/<id>` | JSON version of one report |
| `/healthz` | Liveness check |

## Adding a mountain

Append an entry to [`data/mountains.json`](data/mountains.json) — no code changes needed:

```json
{
  "id": "mount-example",
  "name": "Mount Example",
  "region": "Rockies",
  "state": "CO",
  "country": "US",
  "lat": 39.0,
  "lon": -106.0,
  "base_elevation_m": 2400,
  "summit_elevation_m": 3500,
  "website": "https://example.com"
}
```

`id` must be a lowercase slug and unique; the summit must sit above the base; and
coordinates should be the **base area**, not the nearby town. `region` controls
which group it appears under in the picker — see `REGION_ORDER` in
[`skireport/mountains.py`](skireport/mountains.py). The registry is validated on
load, so a malformed entry fails loudly at startup rather than rendering a broken
page. `pytest tests/test_mountains.py` checks the whole file.

## Units

Imperial throughout. To switch to metric, change `TEMPERATURE_UNIT`,
`WIND_SPEED_UNIT` and `PRECIPITATION_UNIT` at the top of
[`skireport/weather.py`](skireport/weather.py); the unit strings are read back off
the response, so depth conversion follows automatically.

## Caching

Responses are cached in memory for 15 minutes, keyed by mountain and elevation —
Open-Meteo's models only update hourly and the free tier is rate limited. If a
refresh fails, the last good response is served and the page is marked stale rather
than erroring out.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The suite never touches the network: `tests/fixtures/open_meteo_sample.json` is a
real Open-Meteo response with a fixed time axis and known snowfall, monkeypatched
over the HTTP call.

## Caveats

These are **forecast model outputs, not on-mountain measurements**. They will not
match a resort's official snow-stake report exactly, and they say nothing about
lift or trail status — check the resort's own site for that.

## Licence

MIT — see [LICENSE](LICENSE). Weather data © Open-Meteo, licensed CC BY 4.0.
