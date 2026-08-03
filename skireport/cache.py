"""A tiny thread-safe TTL cache.

Open-Meteo's models refresh roughly hourly and the free tier is rate limited, so
repeated page loads should not mean repeated fetches. Entries are kept after they
expire: a failed refresh can fall back to the stale value rather than showing the
user nothing.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar

V = TypeVar("V")

DEFAULT_TTL_SECONDS = 15 * 60


@dataclass(frozen=True)
class Entry(Generic[V]):
    value: V
    stored_at: float

    def age(self, now: float) -> float:
        return now - self.stored_at


class TTLCache(Generic[V]):
    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[Hashable, Entry[V]] = {}
        self._lock = threading.Lock()

    def get(self, key: Hashable) -> V | None:
        """Return the value only while it is fresh."""
        entry = self.get_entry(key)
        if entry is None or entry.age(time.time()) >= self.ttl_seconds:
            return None
        return entry.value

    def get_entry(self, key: Hashable) -> Entry[V] | None:
        """Return the raw entry regardless of age, for stale fallbacks."""
        with self._lock:
            return self._entries.get(key)

    def set(self, key: Hashable, value: V) -> None:
        with self._lock:
            self._entries[key] = Entry(value=value, stored_at=time.time())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
