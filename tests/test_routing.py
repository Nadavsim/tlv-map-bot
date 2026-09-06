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


def test_fetch_eta_seconds_returns_duration_on_success(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"routes": [{"duration": 543.2}]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, timeout: fake_response)

    result = routing._fetch_eta_seconds("walking", (32.08, 34.78), (32.09, 34.79))

    assert result == 543.2


def test_fetch_eta_seconds_uses_the_right_service_per_mode(monkeypatch):
    captured = {}

    def fake_get(url, timeout):
        captured["url"] = url
        response = MagicMock()
        response.json.return_value = {"routes": [{"duration": 100}]}
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    routing._fetch_eta_seconds("driving", (32.08, 34.78), (32.09, 34.79))
    assert "routed-car" in captured["url"]

    routing._fetch_eta_seconds("walking", (32.08, 34.78), (32.09, 34.79))
    assert "routed-foot" in captured["url"]


def test_fetch_eta_seconds_returns_none_on_unknown_mode():
    assert routing._fetch_eta_seconds("teleport", (32.08, 34.78), (32.09, 34.79)) is None


def test_fetch_eta_seconds_returns_none_on_request_failure(monkeypatch):
    def raise_error(url, timeout):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", raise_error)

    assert routing._fetch_eta_seconds("walking", (32.08, 34.78), (32.09, 34.79)) is None


@pytest.mark.asyncio
async def test_get_eta_seconds_delegates_to_fetch(monkeypatch):
    monkeypatch.setattr(routing, "_fetch_eta_seconds", lambda mode, origin, dest: 42.0)

    result = await routing.get_eta_seconds("walking", (32.08, 34.78), (32.09, 34.79))

    assert result == 42.0
