from unittest.mock import MagicMock

import pytest
import requests

import routing


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
