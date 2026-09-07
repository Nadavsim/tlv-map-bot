from unittest.mock import MagicMock

import requests

import location


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
