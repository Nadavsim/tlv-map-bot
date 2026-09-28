import time
from unittest.mock import MagicMock

import pytest
import requests

from backend.services import location


@pytest.fixture(autouse=True)
def reset_geocoding_state():
    # The geocode cache and back-off are module-level, so without this one
    # test's "Rothschild 12" (or a run of simulated failures) would leak into
    # every test after it.
    location._geocode_cache.clear()
    location._geocode_backoff.reset()
    yield
    location._geocode_cache.clear()
    location._geocode_backoff.reset()


def _counting_get(monkeypatch, *, json=None, error=None):
    """Patches requests.get, returning a dict whose "calls" count shows how
    many real network calls the code under test made."""
    state = {"calls": 0}

    def fake_get(url, params, headers, timeout):
        state["calls"] += 1
        if error is not None:
            raise error
        response = MagicMock()
        response.json.return_value = json
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    return state


def test_extracts_coords_from_q_param():
    url = "https://www.google.com/maps?q=32.0653,34.7739"
    assert location.extract_coords_from_url(url) == (32.0653, 34.7739)


def test_extracts_coords_from_at_notation():
    url = "https://www.google.com/maps/@32.0653,34.7739,15z"
    assert location.extract_coords_from_url(url) == (32.0653, 34.7739)


def test_extracts_coords_from_place_url_with_at_notation():
    url = "https://www.google.com/maps/place/Some+Place/@32.0653,34.7739,17z/data=..."
    assert location.extract_coords_from_url(url) == (32.0653, 34.7739)


def test_extracts_coords_from_3d4d_notation():
    url = "https://www.google.com/maps/place/X/data=!4m5!3m4!1s0x0:0x0!8m2!3d32.0653!4d34.7739"
    assert location.extract_coords_from_url(url) == (32.0653, 34.7739)


def test_extracts_negative_coordinates():
    url = "https://www.google.com/maps?q=-33.8688,151.2093"
    assert location.extract_coords_from_url(url) == (-33.8688, 151.2093)


def test_returns_none_when_no_coords_present():
    assert location.extract_coords_from_url("https://www.google.com/maps/search/pizza") is None


def test_prefers_precise_place_pin_over_viewport_center_when_both_present():
    # A real Google Maps place-share URL carries BOTH: @lat,lon is the map
    # viewport center at share time (can be panned/zoomed away from the pin),
    # while !3d!4d is the actual place coordinate. The precise one must win.
    url = (
        "https://www.google.com/maps/place/Some+Bar/@32.0653,34.7739,17z/"
        "data=!4m6!3m5!1s0x0:0x0!8m2!3d32.0700!4d34.7800"
    )
    assert location.extract_coords_from_url(url) == (32.0700, 34.7800)


def test_resolve_maps_link_extracts_directly_without_network_call(monkeypatch):
    called = False

    def fake_get(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(requests, "get", fake_get)

    result = location.resolve_maps_link("https://www.google.com/maps?q=32.0653,34.7739")

    assert result == (32.0653, 34.7739)
    assert called is False


def test_resolve_maps_link_follows_short_link_redirect(monkeypatch):
    fake_response = MagicMock()
    fake_response.url = "https://www.google.com/maps/@32.0653,34.7739,15z"
    monkeypatch.setattr(requests, "get", lambda url, timeout, allow_redirects: fake_response)

    result = location.resolve_maps_link("https://maps.app.goo.gl/abc123")

    assert result == (32.0653, 34.7739)


def test_resolve_maps_link_returns_none_for_plain_text():
    assert location.resolve_maps_link("not a link or coordinates") is None


def test_resolve_maps_link_returns_none_on_request_failure(monkeypatch):
    def raise_error(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", raise_error)

    assert location.resolve_maps_link("https://maps.app.goo.gl/abc123") is None


def test_geocode_address_returns_coords_from_first_result(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = [{"lat": "32.0627450", "lon": "34.7704470"}]
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, params, headers, timeout: fake_response)

    result = location.geocode_address("Rothschild 12")

    assert result == (32.0627450, 34.7704470)


def test_geocode_address_biases_the_query_toward_tel_aviv(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        captured["headers"] = headers
        response = MagicMock()
        response.json.return_value = [{"lat": "32.0", "lon": "34.7"}]
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    location.geocode_address("Rothschild 12")

    assert "Tel Aviv-Yafo" in captured["params"]["q"]
    assert captured["params"]["countrycodes"] == "il"
    assert "User-Agent" in captured["headers"]


def test_geocode_address_returns_none_when_no_results(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = []
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(requests, "get", lambda url, params, headers, timeout: fake_response)

    assert location.geocode_address("asdkfjaslkdfj nonsense") is None


def test_geocode_address_raises_unavailable_on_request_failure(monkeypatch):
    _counting_get(monkeypatch, error=requests.RequestException("boom"))

    with pytest.raises(location.GeocodingUnavailable):
        location.geocode_address("Rothschild 12")


def test_geocode_address_raises_unavailable_on_http_error_status(monkeypatch):
    # e.g. Nominatim answering 429 when it's rate limiting us.
    def fake_get(url, params, headers, timeout):
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError("429")
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(location.GeocodingUnavailable):
        location.geocode_address("Rothschild 12")


def test_geocode_address_raises_unavailable_on_malformed_response(monkeypatch):
    _counting_get(monkeypatch, json=[{"unexpected": "shape"}])

    with pytest.raises(location.GeocodingUnavailable):
        location.geocode_address("Rothschild 12")


def test_geocode_address_caches_successful_lookups(monkeypatch):
    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77"}])

    first = location.geocode_address("Rothschild 12")
    second = location.geocode_address("Rothschild 12")

    assert first == second == (32.06, 34.77)
    assert state["calls"] == 1


def test_geocode_cache_ignores_case_and_extra_whitespace(monkeypatch):
    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77"}])

    location.geocode_address("Rothschild 12")
    location.geocode_address("  rothschild   12 ")

    assert state["calls"] == 1


def test_geocode_does_not_cache_no_result(monkeypatch):
    state = _counting_get(monkeypatch, json=[])

    assert location.geocode_address("nonsense") is None
    assert location.geocode_address("nonsense") is None

    assert state["calls"] == 2


def test_geocode_does_not_cache_a_failure(monkeypatch):
    _counting_get(monkeypatch, error=requests.RequestException("boom"))
    with pytest.raises(location.GeocodingUnavailable):
        location.geocode_address("Rothschild 12")

    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77"}])

    assert location.geocode_address("Rothschild 12") == (32.06, 34.77)
    assert state["calls"] == 1


def test_geocode_backs_off_after_three_consecutive_failures(monkeypatch):
    state = _counting_get(monkeypatch, error=requests.RequestException("boom"))

    for _ in range(3):
        with pytest.raises(location.GeocodingUnavailable):
            location.geocode_address("Rothschild 12")
    assert state["calls"] == 3

    with pytest.raises(location.GeocodingUnavailable):
        location.geocode_address("Dizengoff 50")
    assert state["calls"] == 3  # the fourth attempt never touched the network


def test_geocode_retries_once_the_cooldown_has_passed(monkeypatch):
    fake_time = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])
    _counting_get(monkeypatch, error=requests.RequestException("boom"))
    for _ in range(3):
        with pytest.raises(location.GeocodingUnavailable):
            location.geocode_address("Rothschild 12")

    fake_time[0] += 31
    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77"}])

    assert location.geocode_address("Dizengoff 50") == (32.06, 34.77)
    assert state["calls"] == 1


def test_geocode_no_result_does_not_count_toward_backing_off(monkeypatch):
    # A user typing several unresolvable addresses is not an outage.
    state = _counting_get(monkeypatch, json=[])

    for query in ("nonsense a", "nonsense b", "nonsense c", "nonsense d"):
        assert location.geocode_address(query) is None

    assert state["calls"] == 4


def test_geocode_success_resets_the_failure_count(monkeypatch):
    _counting_get(monkeypatch, error=requests.RequestException("boom"))
    for _ in range(2):
        with pytest.raises(location.GeocodingUnavailable):
            location.geocode_address("a")

    _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77"}])
    location.geocode_address("b")

    state = _counting_get(monkeypatch, error=requests.RequestException("boom"))
    for _ in range(2):
        with pytest.raises(location.GeocodingUnavailable):
            location.geocode_address("c")
    assert state["calls"] == 2  # 2 + 2 failures around a success never reached 3 in a row
