import time

import pytest

from backend.services.resilience import FailureBackoff, TTLCache


@pytest.fixture
def fake_time(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    return now


def test_cache_returns_a_stored_value():
    cache = TTLCache(ttl_seconds=60, max_entries=10)
    cache.set("k", (1.0, 2.0))
    assert cache.get("k") == (1.0, 2.0)


def test_cache_miss_returns_none():
    assert TTLCache(ttl_seconds=60, max_entries=10).get("missing") is None


def test_cache_entry_expires_after_ttl(fake_time):
    cache = TTLCache(ttl_seconds=60, max_entries=10)
    cache.set("k", "v")

    fake_time[0] += 59
    assert cache.get("k") == "v"

    fake_time[0] += 2
    assert cache.get("k") is None


def test_cache_evicts_the_oldest_entry_past_max_entries():
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_cache_overwriting_a_key_refreshes_its_expiry_and_position(fake_time):
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    cache.set("b", 2)
    fake_time[0] += 50
    cache.set("a", 10)  # a is now the newest entry, with a fresh 60s
    cache.set("c", 3)  # evicts b, the oldest

    fake_time[0] += 20
    assert cache.get("a") == 10
    assert cache.get("b") is None


def test_cache_clear_empties_it():
    cache = TTLCache(ttl_seconds=60, max_entries=10)
    cache.set("k", "v")
    cache.clear()
    assert cache.get("k") is None


def test_backoff_starts_closed():
    assert FailureBackoff(threshold=3, cooldown_seconds=30).is_open() is False


def test_backoff_opens_only_at_the_threshold():
    backoff = FailureBackoff(threshold=3, cooldown_seconds=30)
    backoff.record_failure()
    backoff.record_failure()
    assert backoff.is_open() is False

    backoff.record_failure()
    assert backoff.is_open() is True


def test_backoff_closes_after_the_cooldown(fake_time):
    backoff = FailureBackoff(threshold=1, cooldown_seconds=30)
    backoff.record_failure()

    fake_time[0] += 29
    assert backoff.is_open() is True

    fake_time[0] += 2
    assert backoff.is_open() is False


def test_one_failure_after_the_cooldown_reopens_it_immediately(fake_time):
    backoff = FailureBackoff(threshold=3, cooldown_seconds=30)
    for _ in range(3):
        backoff.record_failure()
    fake_time[0] += 31
    assert backoff.is_open() is False

    backoff.record_failure()
    assert backoff.is_open() is True


def test_a_success_fully_resets_the_backoff():
    backoff = FailureBackoff(threshold=2, cooldown_seconds=30)
    backoff.record_failure()
    backoff.record_success()
    backoff.record_failure()

    assert backoff.is_open() is False  # 1 failure since the success, not 2


def test_a_success_closes_an_open_backoff():
    backoff = FailureBackoff(threshold=1, cooldown_seconds=30)
    backoff.record_failure()
    assert backoff.is_open() is True

    backoff.record_success()
    assert backoff.is_open() is False
