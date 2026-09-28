"""Small building blocks for calling free public services (OSRM, Nominatim)
politely: remember answers so repeat lookups don't hit them again, and stop
calling them for a moment once they've clearly stopped answering. Kept
in-process on purpose - this app runs as a single instance (see the
rate-limiter note in app.py), so there's no shared store to justify."""

import threading
import time
from collections import OrderedDict


class TTLCache:
    """Entries expire after `ttl_seconds`; once `max_entries` is reached the
    oldest entry is evicted first. Never store None as a value - get() uses
    None to mean "not cached". Lookups happen from worker threads
    (asyncio.to_thread) as well as the event loop, hence the lock."""

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() >= expires_at:
                del self._entries[key]
                return None
            return value

    def set(self, key, value) -> None:
        with self._lock:
            self._entries.pop(key, None)
            self._entries[key] = (time.monotonic() + self._ttl_seconds, value)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class FailureBackoff:
    """After `threshold` consecutive failures, is_open() reports True for
    `cooldown_seconds` so callers can skip a service that isn't answering
    instead of paying its full timeout on every request. Once the cooldown
    passes, the next call is allowed through; because the failure count is
    still at the threshold, a single further failure re-opens it right away,
    while one success resets it fully."""

    def __init__(self, threshold: int, cooldown_seconds: float) -> None:
        self._threshold = threshold
        self._cooldown_seconds = cooldown_seconds
        self._consecutive_failures = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def is_open(self) -> bool:
        with self._lock:
            return time.monotonic() < self._open_until

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._threshold:
                self._open_until = time.monotonic() + self._cooldown_seconds

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._open_until = 0.0

    def reset(self) -> None:
        self.record_success()
