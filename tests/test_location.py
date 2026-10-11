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
    fake_response.json.return_value = [{"lat": "32.0627450", "lon": "34.7704470", "address": {"city": "תל־אביב–יפו"}}]
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
        response.json.return_value = [{"lat": "32.0", "lon": "34.7", "address": {"city": "תל־אביב–יפו"}}]
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    location.geocode_address("Rothschild 12")

    assert captured["params"]["q"] == "Rothschild 12, Tel Aviv-Yafo"
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
    # An in-area result with no coordinates in it.
    _counting_get(monkeypatch, json=[{"address": {"city": "תל־אביב–יפו"}}])

    with pytest.raises(location.GeocodingUnavailable):
        location.geocode_address("Rothschild 12")


def test_geocode_address_caches_successful_lookups(monkeypatch):
    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77", "address": {"city": "תל־אביב–יפו"}}])

    first = location.geocode_address("Rothschild 12")
    second = location.geocode_address("Rothschild 12")

    assert first == second == (32.06, 34.77)
    assert state["calls"] == 1


def test_geocode_cache_ignores_case_and_extra_whitespace(monkeypatch):
    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77", "address": {"city": "תל־אביב–יפו"}}])

    location.geocode_address("Rothschild 12")
    location.geocode_address("  rothschild   12 ")

    assert state["calls"] == 1


def test_geocode_does_not_cache_no_result(monkeypatch):
    state = _counting_get(monkeypatch, json=[])

    assert location.geocode_address("nonsense") is None
    assert location.geocode_address("nonsense") is None

    assert state["calls"] == 4  # two passes per lookup, none of it cached


def test_geocode_does_not_cache_a_failure(monkeypatch):
    _counting_get(monkeypatch, error=requests.RequestException("boom"))
    with pytest.raises(location.GeocodingUnavailable):
        location.geocode_address("Rothschild 12")

    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77", "address": {"city": "תל־אביב–יפו"}}])

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
    state = _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77", "address": {"city": "תל־אביב–יפו"}}])

    assert location.geocode_address("Dizengoff 50") == (32.06, 34.77)
    assert state["calls"] == 1


def test_geocode_no_result_does_not_count_toward_backing_off(monkeypatch):
    # A user typing several unresolvable addresses is not an outage.
    state = _counting_get(monkeypatch, json=[])

    for query in ("nonsense a", "nonsense b", "nonsense c", "nonsense d"):
        assert location.geocode_address(query) is None

    assert state["calls"] == 8  # two passes each


def test_geocode_success_resets_the_failure_count(monkeypatch):
    _counting_get(monkeypatch, error=requests.RequestException("boom"))
    for _ in range(2):
        with pytest.raises(location.GeocodingUnavailable):
            location.geocode_address("a")

    _counting_get(monkeypatch, json=[{"lat": "32.06", "lon": "34.77", "address": {"city": "תל־אביב–יפו"}}])
    location.geocode_address("b")

    state = _counting_get(monkeypatch, error=requests.RequestException("boom"))
    for _ in range(2):
        with pytest.raises(location.GeocodingUnavailable):
            location.geocode_address("c")
    assert state["calls"] == 2  # 2 + 2 failures around a success never reached 3 in a row


# --- links that carry a place name but no coordinates ----------------------

import pytest

_HEBREW_PLACE_URL = (
    "https://www.google.com/maps/place/"
    "%D7%9E%D7%99%D7%98+%D7%91%D7%A8,+Shlomo+Ibn+Gabirol+St+67,+Tel+Aviv-Yafo,+6436214%E2%80%AD"
    "/data=!4m2!3m1!1s0x151d4bf4a15a9be5:0x424fb72bc743cd81?utm_source=mstt_1"
)


@pytest.mark.parametrize(
    "url,expected",
    [
        (_HEBREW_PLACE_URL, "\u05de\u05d9\u05d8 \u05d1\u05e8, Shlomo Ibn Gabirol St 67, Tel Aviv-Yafo, 6436214"),
        ("https://www.google.com/maps/place/Dizengoff+Square,+Tel+Aviv-Yafo", "Dizengoff Square, Tel Aviv-Yafo"),
        ("https://www.google.com/maps/place/Cafe+Xoho/@32.07,34.77,17z/data=!3m1", "Cafe Xoho"),
        ("https://www.google.com/maps?q=Dizengoff+Square", "Dizengoff Square"),
        ("https://www.google.com/maps/search/?api=1&query=Dizengoff+Square", "Dizengoff Square"),
        ("https://www.google.com/maps/search/Dizengoff+square", "Dizengoff square"),
        ("https://www.google.co.il/maps/place/Foo", "Foo"),
        ("https://maps.google.com/?q=Foo+Bar", "Foo Bar"),
    ],
)
def test_extract_place_text_from_url(url, expected):
    assert location.extract_place_text_from_url(url) == expected


def test_extract_place_text_strips_invisible_bidi_marks():
    # Google appends U+202D to right-to-left place names.
    assert "\u202d" not in location.extract_place_text_from_url(_HEBREW_PLACE_URL)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/maps/place/Evil+Corp",  # not a Google host
        "https://www.google.com.evil.example/maps/place/Foo",  # lookalike host
        "https://www.google.com/maps/@32.0653,34.7739,15z",  # coordinates only
        "https://www.google.com/maps?q=32.0653,34.7739",  # q is a coordinate pair
        "https://maps.app.goo.gl/abc123",  # an unexpanded short link has no text
        "not a url",
    ],
)
def test_extract_place_text_returns_none_when_there_is_nothing_usable(url):
    assert location.extract_place_text_from_url(url) is None


def test_resolve_maps_link_detail_returns_place_text_when_the_expanded_url_has_no_coordinates(monkeypatch):
    fake_response = MagicMock()
    fake_response.url = _HEBREW_PLACE_URL
    monkeypatch.setattr(requests, "get", lambda url, timeout, allow_redirects: fake_response)

    coords, place_text = location.resolve_maps_link_detail("https://maps.app.goo.gl/abc123")

    assert coords is None
    assert place_text.startswith("\u05de\u05d9\u05d8 \u05d1\u05e8, Shlomo Ibn Gabirol")


def test_resolve_maps_link_detail_returns_both_when_the_expanded_url_has_them(monkeypatch):
    fake_response = MagicMock()
    fake_response.url = "https://www.google.com/maps/place/Cafe+Xoho/@32.07,34.77,17z/data=!3m1"
    monkeypatch.setattr(requests, "get", lambda url, timeout, allow_redirects: fake_response)

    assert location.resolve_maps_link_detail("https://maps.app.goo.gl/abc123") == ((32.07, 34.77), "Cafe Xoho")


def test_resolve_maps_link_detail_keeps_the_text_when_the_request_fails(monkeypatch):
    def raise_error(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", raise_error)

    url = "https://www.google.com/maps/place/Dizengoff+Square"
    assert location.resolve_maps_link_detail(url) == (None, "Dizengoff Square")


def test_resolve_maps_link_detail_for_plain_text_does_nothing(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no request expected for plain text")

    monkeypatch.setattr(requests, "get", fail)
    assert location.resolve_maps_link_detail("Dizengoff square") == (None, None)


def test_geocode_candidates_goes_from_full_text_to_name_to_address():
    text = "Meat Bar, Shlomo Ibn Gabirol St 67, Tel Aviv-Yafo, 6436214"
    assert location.geocode_candidates(text) == [
        "Meat Bar, Shlomo Ibn Gabirol St 67, Tel Aviv-Yafo",
        "Meat Bar",
        "Shlomo Ibn Gabirol St 67, Tel Aviv-Yafo",
    ]


def test_geocode_candidates_for_a_single_part_is_just_that_part():
    assert location.geocode_candidates("Dizengoff Square") == ["Dizengoff Square"]


# --- the area restriction (Tel Aviv-Yafo, Ramat Gan, Givatayim) -------------

_TLV = "\u05ea\u05dc\u05be\u05d0\u05d1\u05d9\u05d1\u2013\u05d9\u05e4\u05d5"
_RAMAT_GAN = "\u05e8\u05de\u05ea \u05d2\u05df"
_GIVATAYIM = "\u05d2\u05d1\u05e2\u05ea\u05d9\u05d9\u05dd"
_BAT_YAM = "\u05d1\u05ea \u05d9\u05dd"


def _row(lat, lon, **address):
    return {"lat": str(lat), "lon": str(lon), "address": address}


def _scripted_get(monkeypatch, *pages):
    """Each network call gets the next page of results; records the params."""
    state = {"params": [], "pages": list(pages)}

    def fake_get(url, params, headers, timeout):
        state["params"].append(params)
        response = MagicMock()
        response.json.return_value = state["pages"].pop(0) if state["pages"] else []
        response.raise_for_status.return_value = None
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    return state


def test_geocode_restricts_the_lookup_to_the_area_box(monkeypatch):
    state = _scripted_get(monkeypatch, [_row(32.06, 34.77, city=_TLV)])

    location.geocode_address("Rothschild 12")

    params = state["params"][0]
    assert params["bounded"] == 1
    assert params["viewbox"] == location._AREA_VIEWBOX
    assert params["addressdetails"] == 1
    assert params["limit"] == 5


def test_geocode_area_box_actually_contains_the_three_cities():
    left, top, right, bottom = (float(v) for v in location._AREA_VIEWBOX.split(","))
    landmarks = {  # (lat, lon): rough, deliberately near the edges
        "Ramat Aviv (north TLV)": (32.115, 34.80),
        "Jaffa (south TLV)": (32.03, 34.75),
        "Bar-Ilan side of Ramat Gan": (32.07, 34.84),
        "Givatayim": (32.07, 34.81),
        "Dizengoff Square": (32.078, 34.774),
    }
    for name, (lat, lon) in landmarks.items():
        assert left <= lon <= right and bottom <= lat <= top, name


@pytest.mark.parametrize(
    "address",
    [
        {"city": _TLV},
        {"town": _RAMAT_GAN},
        {"town": _GIVATAYIM},
        {"city": "Tel Aviv-Yafo"},
        {"town": "Ramat Gan"},
        {"town": "Givatayim"},
        {"city": "Tel Aviv-Jaffa"},
    ],
)
def test_geocode_accepts_the_three_areas_in_hebrew_and_english(monkeypatch, address):
    _scripted_get(monkeypatch, [{"lat": "32.07", "lon": "34.78", "address": address}])

    assert location.geocode_address("somewhere") == (32.07, 34.78)


@pytest.mark.parametrize(
    "address",
    [
        {"town": _BAT_YAM},
        {"town": "\u05d7\u05d5\u05dc\u05d5\u05df"},  # Holon
        {"town": "\u05d1\u05e0\u05d9 \u05d1\u05e8\u05e7"},  # Bnei Brak - inside the rectangle
        {"town": "\u05e7\u05e8\u05d9\u05d9\u05ea \u05d0\u05d5\u05e0\u05d5"},  # Kiryat Ono
        {"city": "Haifa"},
        {},  # no municipality at all is not trusted
    ],
)
def test_geocode_rejects_results_from_other_municipalities(monkeypatch, address):
    state = _scripted_get(monkeypatch, [{"lat": "32.02", "lon": "34.74", "address": address}])

    assert location.geocode_address("Rothschild 12") is None
    assert len(state["params"]) == 2  # tried both passes before giving up


def test_geocode_skips_an_out_of_area_hit_for_an_in_area_one_further_down(monkeypatch):
    # Seen live: unbiased "Rothschild 12" ranks Bat Yam and Holon first.
    _scripted_get(
        monkeypatch,
        [_row(32.026, 34.743, town=_BAT_YAM), _row(32.0627, 34.7704, city=_TLV)],
    )

    assert location.geocode_address("Rothschild 12") == (32.0627, 34.7704)


def test_geocode_tries_the_text_as_typed_when_the_biased_pass_finds_nothing(monkeypatch):
    # A street that only exists in Ramat Gan: no Tel Aviv-biased hit, then it
    # is found as typed.
    state = _scripted_get(monkeypatch, [], [_row(32.085, 34.8104, town=_RAMAT_GAN)])

    assert location.geocode_address("Hamasger 5") == (32.085, 34.8104)
    assert [p["q"] for p in state["params"]] == ["Hamasger 5, Tel Aviv-Yafo", "Hamasger 5"]


def test_geocode_stops_after_the_first_pass_that_hits(monkeypatch):
    state = _scripted_get(monkeypatch, [_row(32.06, 34.77, city=_TLV)])

    location.geocode_address("Rothschild 12")

    assert len(state["params"]) == 1


@pytest.mark.parametrize(
    "text",
    [
        "Jabotinsky 50 Ramat Gan",
        "Jabotinsky 50, Ramat-Gan",
        "ז'בוטינסקי 50 רמת גן",
        "Weizmann 20 Givatayim",
        "Weizmann 20 Givataim",
        "Dizengoff 50, Tel Aviv",
        "Clock Tower Jaffa",
    ],
)
def test_geocode_does_not_append_tel_aviv_to_text_that_names_an_area(monkeypatch, text):
    # "...Ramat Gan, Tel Aviv-Yafo" contradicted itself and found nothing.
    state = _scripted_get(monkeypatch, [_row(32.08, 34.81, town=_RAMAT_GAN)])

    location.geocode_address(text)

    assert [p["q"] for p in state["params"]] == [text]


def test_geocode_still_biases_text_that_names_no_area(monkeypatch):
    state = _scripted_get(monkeypatch, [_row(32.06, 34.77, city=_TLV)])

    location.geocode_address("Bialik 10")

    assert state["params"][0]["q"] == "Bialik 10, Tel Aviv-Yafo"


def test_normalize_name_ignores_hebrew_hyphen_variants_and_spacing():
    assert (
        location._normalize_name("\u05ea\u05dc\u05be\u05d0\u05d1\u05d9\u05d1\u2013\u05d9\u05e4\u05d5")
        == location._normalize_name("\u05ea\u05dc \u05d0\u05d1\u05d9\u05d1-\u05d9\u05e4\u05d5")
    )
    assert location._normalize_name("Tel Aviv-Yafo") == location._normalize_name("tel  aviv - yafo")
