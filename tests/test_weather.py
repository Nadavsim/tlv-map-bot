from unittest.mock import MagicMock

import pytest
import requests

from backend.services import weather


@pytest.fixture(autouse=True)
def reset_weather_cache():
    weather._cache_expires_at = 0.0
    weather._cache_value = False
    yield
    weather._cache_expires_at = 0.0
    weather._cache_value = False


def test_fetch_is_raining_true_when_precipitation_is_positive(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"current": {"precipitation": 1.2}}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda *a, **kw: fake_response)

    assert weather._fetch_is_raining(32.08, 34.78) is True


def test_fetch_is_raining_false_when_precipitation_is_zero(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"current": {"precipitation": 0.0}}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda *a, **kw: fake_response)

    assert weather._fetch_is_raining(32.08, 34.78) is False


def test_fetch_is_raining_false_on_request_failure(monkeypatch):
    def raise_error(*a, **kw):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", raise_error)

    assert weather._fetch_is_raining(32.08, 34.78) is False


def test_fetch_is_raining_false_on_malformed_response(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"unexpected": "shape"}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda *a, **kw: fake_response)

    assert weather._fetch_is_raining(32.08, 34.78) is False


@pytest.mark.asyncio
async def test_is_raining_now_delegates_to_fetch(monkeypatch):
    monkeypatch.setattr(weather, "_fetch_is_raining", lambda lat, lon: True)
    assert await weather.is_raining_now(32.08, 34.78) is True


@pytest.mark.asyncio
async def test_is_raining_now_caches_between_calls(monkeypatch):
    call_count = 0

    def fake_fetch(lat, lon):
        nonlocal call_count
        call_count += 1
        return True

    monkeypatch.setattr(weather, "_fetch_is_raining", fake_fetch)

    first = await weather.is_raining_now(32.08, 34.78)
    second = await weather.is_raining_now(32.08, 34.78)

    assert first is True
    assert second is True
    assert call_count == 1


@pytest.mark.asyncio
async def test_is_raining_now_refetches_after_ttl_expires(monkeypatch):
    import time

    monkeypatch.setattr(weather, "_fetch_is_raining", lambda lat, lon: True)

    fake_time = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])

    await weather.is_raining_now(32.08, 34.78)
    fake_time[0] += weather._CACHE_TTL_SECONDS + 1

    call_count = 0

    def fake_fetch(lat, lon):
        nonlocal call_count
        call_count += 1
        return False

    monkeypatch.setattr(weather, "_fetch_is_raining", fake_fetch)
    result = await weather.is_raining_now(32.08, 34.78)

    assert result is False
    assert call_count == 1
