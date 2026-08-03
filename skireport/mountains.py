"""The ski mountain registry.

Resorts live in ``data/mountains.json`` so adding one is a data edit, not a code
change. The file is loaded and validated once on first access.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "mountains.json"

# Region display order for the picker; anything unlisted is appended alphabetically.
REGION_ORDER = [
    "Rockies",
    "California & Sierra",
    "Pacific Northwest",
    "Northeast",
    "Canada",
]

_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_METRES_PER_FOOT = 0.3048


class RegistryError(ValueError):
    """Raised when mountains.json is malformed."""


@dataclass(frozen=True)
class Mountain:
    id: str
    name: str
    region: str
    state: str
    country: str
    lat: float
    lon: float
    base_elevation_m: int
    summit_elevation_m: int
    website: str

    @property
    def vertical_m(self) -> int:
        return self.summit_elevation_m - self.base_elevation_m

    @property
    def base_elevation_ft(self) -> int:
        return round(self.base_elevation_m / _METRES_PER_FOOT)

    @property
    def summit_elevation_ft(self) -> int:
        return round(self.summit_elevation_m / _METRES_PER_FOOT)

    @property
    def vertical_ft(self) -> int:
        return round(self.vertical_m / _METRES_PER_FOOT)


def _build(raw: object, index: int) -> Mountain:
    if not isinstance(raw, dict):
        raise RegistryError(f"entry {index} is not an object")

    missing = {f.name for f in Mountain.__dataclass_fields__.values()} - raw.keys()
    if missing:
        raise RegistryError(f"entry {index} is missing {sorted(missing)}")

    mountain = Mountain(
        id=str(raw["id"]),
        name=str(raw["name"]),
        region=str(raw["region"]),
        state=str(raw["state"]),
        country=str(raw["country"]),
        lat=float(raw["lat"]),
        lon=float(raw["lon"]),
        base_elevation_m=int(raw["base_elevation_m"]),
        summit_elevation_m=int(raw["summit_elevation_m"]),
        website=str(raw["website"]),
    )

    if not _SLUG.match(mountain.id):
        raise RegistryError(f"id {mountain.id!r} is not a lowercase slug")
    if not -90 <= mountain.lat <= 90 or not -180 <= mountain.lon <= 180:
        raise RegistryError(f"{mountain.id} has coordinates outside valid range")
    if mountain.summit_elevation_m <= mountain.base_elevation_m:
        raise RegistryError(f"{mountain.id} summit elevation is not above its base")

    return mountain


def _load(path: Path = DATA_FILE) -> dict[str, Mountain]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"registry not found at {path}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry is not valid JSON: {exc}") from exc

    if not isinstance(raw, list):
        raise RegistryError("registry must be a JSON array")

    registry: dict[str, Mountain] = {}
    for index, entry in enumerate(raw):
        mountain = _build(entry, index)
        if mountain.id in registry:
            raise RegistryError(f"duplicate id {mountain.id!r}")
        registry[mountain.id] = mountain

    if not registry:
        raise RegistryError("registry is empty")
    return registry


_REGISTRY: dict[str, Mountain] | None = None


def _registry() -> dict[str, Mountain]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _load()
    return _REGISTRY


def all_mountains() -> list[Mountain]:
    """Every mountain, sorted by name."""
    return sorted(_registry().values(), key=lambda m: m.name)


def get(mountain_id: str) -> Mountain | None:
    """Look up one mountain, or ``None`` if the id is unknown."""
    return _registry().get(mountain_id)


def by_region() -> dict[str, list[Mountain]]:
    """Mountains grouped for the picker, regions in :data:`REGION_ORDER`."""
    grouped: dict[str, list[Mountain]] = {}
    for mountain in all_mountains():
        grouped.setdefault(mountain.region, []).append(mountain)

    def sort_key(region: str) -> tuple[int, str]:
        try:
            return (REGION_ORDER.index(region), "")
        except ValueError:
            return (len(REGION_ORDER), region)

    return {region: grouped[region] for region in sorted(grouped, key=sort_key)}
