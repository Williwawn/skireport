import json
import re

import pytest

from conftest import log
from skireport import mountains
from skireport.mountains import RegistryError, _load


def test_registry_loads():
    everything = mountains.all_mountains()
    by_region = mountains.by_region()
    log.info(
        "registry: %d mountains across %d regions (%s)",
        len(everything),
        len(by_region),
        ", ".join(f"{r} {len(v)}" for r, v in by_region.items()),
    )
    assert len(everything) >= 40


def test_ids_are_unique_slugs():
    ids = [m.id for m in mountains.all_mountains()]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids)


def test_every_entry_is_geographically_sane():
    for m in mountains.all_mountains():
        assert -90 <= m.lat <= 90
        assert -180 <= m.lon <= 180
        assert m.summit_elevation_m > m.base_elevation_m
        assert m.website.startswith("https://")
        assert m.country in {"US", "CA"}


def test_get_known_and_unknown():
    assert mountains.get("jackson-hole").name == "Jackson Hole"
    assert mountains.get("not-a-mountain") is None


def test_by_region_is_ordered_and_complete():
    grouped = mountains.by_region()
    assert list(grouped)[:2] == ["Rockies", "California & Sierra"]
    assert sum(len(v) for v in grouped.values()) == len(mountains.all_mountains())


def test_elevation_conversion():
    whistler = mountains.get("whistler-blackcomb")
    # 675 m base -> ~2,215 ft
    assert whistler.base_elevation_ft == pytest.approx(2215, abs=2)
    assert whistler.vertical_m == 2284 - 675


def _write(tmp_path, entries):
    path = tmp_path / "mountains.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


VALID = {
    "id": "test-hill",
    "name": "Test Hill",
    "region": "Rockies",
    "state": "CO",
    "country": "US",
    "lat": 39.0,
    "lon": -106.0,
    "base_elevation_m": 2000,
    "summit_elevation_m": 3000,
    "website": "https://example.com",
}


def test_rejects_missing_field(tmp_path):
    broken = {k: v for k, v in VALID.items() if k != "lat"}
    with pytest.raises(RegistryError, match="missing"):
        _load(_write(tmp_path, [broken]))


def test_rejects_summit_below_base(tmp_path):
    broken = VALID | {"summit_elevation_m": 1000}
    with pytest.raises(RegistryError, match="summit elevation"):
        _load(_write(tmp_path, [broken]))


def test_rejects_duplicate_ids(tmp_path):
    with pytest.raises(RegistryError, match="duplicate"):
        _load(_write(tmp_path, [VALID, VALID]))


def test_rejects_bad_slug(tmp_path):
    with pytest.raises(RegistryError, match="slug"):
        _load(_write(tmp_path, [VALID | {"id": "Test Hill"}]))
