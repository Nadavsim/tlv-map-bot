import logging
from unittest.mock import MagicMock

import pytest
import requests

from backend.services import routing


@pytest.fixture(autouse=True)
def reset_routing_state():
    # The ETA cache and OSRM back-off are module-level - without this, one
    # test's cached durations or simulated outage would leak into the next.
    routing._eta_cache.clear()
    routing._osrm_backoff.reset()
    yield
    routing._eta_cache.clear()
    routing._osrm_backoff.reset()


def test_format_duration_under_a_minute():
    assert routing.format_duration(30) == "<1 min"


def test_format_duration_minutes():
    assert routing.format_duration(12 * 60) == "12 min"


def test_format_duration_rounds_to_nearest_minute():
    assert routing.format_duration(12 * 60 + 40) == "13 min"


def test_format_duration_hours_and_minutes():
    assert routing.format_duration(65 * 60) == "1h 5min"


def test_format_duration_whole_hours():
    assert routing.format_duration(120 * 60) == "2h"


def test_fetch_eta_seconds_batch_returns_durations_aligned_with_destinations(monkeypatch):
    # Row 0 is origin->everything, including origin->origin (index 0, always
    # 0/self); the function must drop that self-distance and keep the rest
    # aligned with the destinations list passed in.
    fake_response = MagicMock()
    fake_response.json.return_value = {"durations": [[0.0, 543.2, 120.0, None]]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, timeout: fake_response)

    result = routing._fetch_eta_seconds_batch(
        "walking", (32.08, 34.78), [(32.09, 34.79), (32.10, 34.80), (32.11, 34.81)]
    )

    assert result == [543.2, 120.0, None]


def test_fetch_eta_seconds_batch_uses_the_right_service_per_mode(monkeypatch):
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        response = MagicMock()
        response.json.return_value = {"durations": [[100]]}
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    routing._fetch_eta_seconds_batch("driving", (32.08, 34.78), [(32.09, 34.79)])
    assert "routed-car" in captured["url"]
    assert "/table/v1/" in captured["url"]

    routing._fetch_eta_seconds_batch("walking", (32.08, 34.78), [(32.09, 34.79)])
    assert "routed-foot" in captured["url"]


def test_fetch_eta_seconds_batch_returns_none_list_on_unknown_mode():
    result = routing._fetch_eta_seconds_batch("teleport", (32.08, 34.78), [(32.09, 34.79), (32.10, 34.80)])
    assert result == [None, None]


def test_fetch_eta_seconds_batch_returns_none_list_on_request_failure(monkeypatch):
    def raise_error(url, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", raise_error)

    result = routing._fetch_eta_seconds_batch("walking", (32.08, 34.78), [(32.09, 34.79), (32.10, 34.80)])
    assert result == [None, None]


@pytest.mark.asyncio
async def test_get_eta_seconds_batch_delegates_to_fetch(monkeypatch):
    monkeypatch.setattr(routing, "_fetch_eta_seconds_batch", lambda mode, origin, dests: [42.0, 43.0])

    result = await routing.get_eta_seconds_batch("walking", (32.08, 34.78), [(32.09, 34.79), (32.10, 34.80)])

    assert result == [42.0, 43.0]


@pytest.mark.asyncio
async def test_get_eta_seconds_batch_returns_empty_list_for_no_destinations():
    result = await routing.get_eta_seconds_batch("walking", (32.08, 34.78), [])
    assert result == []


def _fetch_recorder(monkeypatch, durations_by_destination):
    """Replaces the network fetch, recording which destinations it was asked
    for. Unknown destinations come back as None (unreachable)."""
    requested = []

    def fake_fetch(mode, origin, destinations):
        requested.append(list(destinations))
        return [durations_by_destination.get(d) for d in destinations]

    monkeypatch.setattr(routing, "_fetch_eta_seconds_batch", fake_fetch)
    return requested


ORIGIN = (32.08, 34.78)
DEST_A, DEST_B, DEST_C = (32.09, 34.79), (32.10, 34.80), (32.11, 34.81)


@pytest.mark.asyncio
async def test_eta_results_are_cached_between_identical_requests(monkeypatch):
    requested = _fetch_recorder(monkeypatch, {DEST_A: 100.0, DEST_B: 200.0})

    first = await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_A, DEST_B])
    second = await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_A, DEST_B])

    assert first == second == [100.0, 200.0]
    assert requested == [[DEST_A, DEST_B]]


@pytest.mark.asyncio
async def test_overlapping_request_only_fetches_the_destinations_not_yet_cached(monkeypatch):
    requested = _fetch_recorder(monkeypatch, {DEST_A: 100.0, DEST_B: 200.0, DEST_C: 300.0})

    await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_A, DEST_B])
    result = await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_B, DEST_C])

    assert result == [200.0, 300.0]
    assert requested == [[DEST_A, DEST_B], [DEST_C]]


@pytest.mark.asyncio
async def test_unreachable_or_failed_destinations_are_not_cached(monkeypatch):
    requested = _fetch_recorder(monkeypatch, {})

    assert await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_A]) == [None]
    assert await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_A]) == [None]

    assert requested == [[DEST_A], [DEST_A]]


@pytest.mark.asyncio
async def test_eta_cache_is_separate_per_mode_and_origin(monkeypatch):
    requested = _fetch_recorder(monkeypatch, {DEST_A: 100.0})

    await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_A])
    await routing.get_eta_seconds_batch("driving", ORIGIN, [DEST_A])
    await routing.get_eta_seconds_batch("walking", (32.20, 34.90), [DEST_A])

    assert len(requested) == 3


@pytest.mark.asyncio
async def test_eta_cache_key_absorbs_float_noise(monkeypatch):
    requested = _fetch_recorder(monkeypatch, {DEST_A: 100.0})

    await routing.get_eta_seconds_batch("walking", ORIGIN, [DEST_A])
    await routing.get_eta_seconds_batch("walking", (32.080000001, 34.780000001), [DEST_A])

    assert len(requested) == 1


def _failing_get(monkeypatch):
    state = {"calls": 0}

    def fake_get(url, timeout):
        state["calls"] += 1
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", fake_get)
    return state


def test_osrm_backs_off_after_three_consecutive_failures(monkeypatch):
    state = _failing_get(monkeypatch)

    for _ in range(3):
        assert routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A]) == [None]
    assert state["calls"] == 3

    assert routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A, DEST_B]) == [None, None]
    assert state["calls"] == 3  # skipped the network entirely


def test_osrm_call_resumes_once_the_cooldown_has_passed(monkeypatch):
    import time

    fake_time = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
    _failing_get(monkeypatch)
    for _ in range(3):
        routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])

    fake_time[0] += 31
    fake_response = MagicMock()
    fake_response.json.return_value = {"durations": [[0.0, 123.0]]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, timeout: fake_response)

    assert routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A]) == [123.0]


def test_unknown_mode_does_not_count_toward_backing_off(monkeypatch):
    for _ in range(5):
        routing._fetch_eta_seconds_batch("teleport", ORIGIN, [DEST_A])

    fake_response = MagicMock()
    fake_response.json.return_value = {"durations": [[0.0, 50.0]]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, timeout: fake_response)

    assert routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A]) == [50.0]


def test_osrm_request_caps_how_long_a_stall_can_cost(monkeypatch):
    # The whole point of the short timeout: a stalled call must not hold a chat
    # reply for the old 5s. Asserts ceilings rather than exact values so
    # tuning within the intent doesn't break it.
    captured = {}

    def fake_get(url, timeout):
        captured["timeout"] = timeout
        response = MagicMock()
        response.json.return_value = {"durations": [[0.0, 10.0]]}
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])

    connect, read = captured["timeout"]
    assert connect <= 2
    assert read <= 3


def test_a_read_timeout_returns_no_eta_and_counts_toward_backing_off(monkeypatch):
    state = {"calls": 0}

    def fake_get(url, timeout):
        state["calls"] += 1
        raise requests.ReadTimeout("stalled")

    monkeypatch.setattr(requests, "get", fake_get)

    for _ in range(3):
        assert routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A]) == [None]
    routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])

    assert state["calls"] == 3  # the fourth was skipped by the back-off


def _osrm_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == routing.logger.name]


def test_a_successful_call_logs_one_ok_line_with_timing(monkeypatch, caplog):
    fake_response = MagicMock()
    fake_response.json.return_value = {"durations": [[0.0, 50.0]]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, timeout: fake_response)

    with caplog.at_level(logging.INFO, logger=routing.logger.name):
        routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])

    (line,) = _osrm_lines(caplog)
    assert "outcome=ok" in line
    assert "mode=walking" in line
    assert "destinations=1" in line
    assert "ms=" in line


def test_a_timeout_is_logged_distinctly_from_other_errors(monkeypatch, caplog):
    def raise_timeout(url, timeout):
        raise requests.ReadTimeout("stalled")

    monkeypatch.setattr(requests, "get", raise_timeout)
    with caplog.at_level(logging.INFO, logger=routing.logger.name):
        routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])
        routing._osrm_backoff.reset()

        def raise_error(url, timeout):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "get", raise_error)
        routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])

    first, second = _osrm_lines(caplog)
    assert "outcome=timeout" in first
    assert "outcome=error" in second


def test_a_skipped_call_is_logged_without_a_duration(monkeypatch, caplog):
    for _ in range(3):
        routing._osrm_backoff.record_failure()

    with caplog.at_level(logging.INFO, logger=routing.logger.name):
        routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])

    (line,) = _osrm_lines(caplog)
    assert "outcome=skipped_backoff" in line
    assert "ms=" not in line


def test_timing_lines_never_contain_coordinates(monkeypatch, caplog):
    # The privacy policy promises locations are never stored - logs are storage.
    fake_response = MagicMock()
    fake_response.json.return_value = {"durations": [[0.0, 50.0]]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, timeout: fake_response)

    with caplog.at_level(logging.INFO, logger=routing.logger.name):
        routing._fetch_eta_seconds_batch("walking", ORIGIN, [DEST_A])

    text = " ".join(_osrm_lines(caplog))
    assert "32.08" not in text and "34.78" not in text
    assert "32.09" not in text and "34.79" not in text
