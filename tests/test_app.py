from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import db
from backend.app import format_place
from backend.models import GeoPoint, PlaceResult, User
from backend.services import auth, llm, location, routing

SAMPLE_PLACE = PlaceResult(
    name="Cafelix",
    category="coffee",
    distance=850,
    instagram_url=None,
    location=GeoPoint(coordinates=(34.77, 32.06)),
)


@pytest.fixture(autouse=True)
def _default_no_dietary_tags(monkeypatch):
    # /api/chat always fetches the known dietary tags now - most tests don't
    # care about dietary tags at all, so default to "none exist" and let the
    # handful that do override this per-test.
    monkeypatch.setattr(db, "get_dietary_tags", AsyncMock(return_value=[]))


def test_health_endpoint_returns_ok_when_database_is_reachable(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "ping_database", AsyncMock(return_value=True))
    with TestClient(app_module.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_answers_head_requests_for_uptime_monitors(monkeypatch):
    # Free-plan uptime monitors send HEAD; a 405 would make the app look down.
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "ping_database", AsyncMock(return_value=True))

    with TestClient(app_module.app) as client:
        resp = client.head("/health")

    assert resp.status_code == 200
    assert resp.content == b""


def test_health_endpoint_head_reports_503_when_database_is_unreachable(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "ping_database", AsyncMock(return_value=False))

    with TestClient(app_module.app) as client:
        resp = client.head("/health")

    assert resp.status_code == 503


def test_health_endpoint_returns_503_when_database_is_unreachable(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "ping_database", AsyncMock(return_value=False))
    with TestClient(app_module.app) as client:
        response = client.get("/health")
    assert response.status_code == 503


def test_format_place_shows_meters_as_km_with_two_decimals_under_1km():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["distance"] == "0.85 km"


def test_format_place_shows_one_decimal_over_1km():
    place = SAMPLE_PLACE.model_copy(update={"distance": 16500})
    formatted = format_place(place, eta_seconds=None)
    assert formatted["distance"] == "16.5 km"


def test_format_place_builds_keyless_maps_deep_link():
    place = SAMPLE_PLACE.model_copy(update={"instagram_url": "https://www.instagram.com/cafelix/"})
    formatted = format_place(place, eta_seconds=None)
    assert formatted["maps_url"] == "https://www.google.com/maps/dir/?api=1&destination=32.06,34.77"
    assert formatted["instagram_url"] == "https://www.instagram.com/cafelix/"


def test_format_place_includes_eta_when_available():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=600)
    assert formatted["eta"] == "10 min"


def test_format_place_eta_is_none_when_routing_failed():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["eta"] is None


def test_format_place_includes_price_tier_when_set():
    place = SAMPLE_PLACE.model_copy(update={"price_tier": "$$"})
    formatted = format_place(place, eta_seconds=None)
    assert formatted["price_tier"] == "$$"


def test_format_place_price_tier_is_none_when_unset():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["price_tier"] is None


def test_format_place_includes_closes_at_hour_when_set():
    place = SAMPLE_PLACE.model_copy(update={"closes_at_hour": 23})
    formatted = format_place(place, eta_seconds=None)
    assert formatted["closes_at_hour"] == 23


def test_format_place_closes_at_hour_is_none_when_unset():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["closes_at_hour"] is None


def test_format_place_includes_outdoor_seating():
    place = SAMPLE_PLACE.model_copy(update={"outdoor_seating": True})
    formatted = format_place(place, eta_seconds=None)
    assert formatted["outdoor_seating"] is True


def test_format_place_outdoor_seating_defaults_to_false():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["outdoor_seating"] is False


def test_chat_endpoint_returns_clarifying_question_when_llm_finds_no_match(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee", "burger"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": None,
                "clarifying_question": "What are you craving?",
                "any_category": False,
            }
        ),
    )
    log_unmatched_mock = AsyncMock()
    monkeypatch.setattr(db, "log_unmatched_query", log_unmatched_mock)
    record_stat_mock = AsyncMock()
    monkeypatch.setattr(db, "record_category_request", record_stat_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "asdkfjalskdjf", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "What are you craving?"
    assert body["places"] == []
    log_unmatched_mock.assert_awaited_once_with("asdkfjalskdjf")
    record_stat_mock.assert_awaited_once_with(db.UNMATCHED_KEY)


def test_chat_endpoint_returns_nearest_places_on_match(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
            }
        ),
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    record_stat_mock = AsyncMock()
    monkeypatch.setattr(db, "record_category_request", record_stat_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "flat white", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert "coffee" in body["reply"]
    assert body["places"][0]["name"] == "Cafelix"
    # Distance only: the ETA is fetched separately (/api/etas).
    assert body["places"][0]["eta"] is None
    assert body["places"][0]["distance"]
    assert body["category"] == "coffee"
    record_stat_mock.assert_awaited_once_with("coffee")


def test_chat_endpoint_replies_in_hebrew_when_lang_is_he(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    parse_mock = AsyncMock(
        return_value={
            "category": "coffee",
            "dietary_tag": None,
            "price_tier": None,
            "clarifying_question": None,
            "any_category": False,
        }
    )
    monkeypatch.setattr(llm, "parse_food_request", parse_mock)
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat", json={"message": "קפה", "lat": 32.08, "lon": 34.78, "lang": "he"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == app_module.REPLIES["he"]["matched"].format(category="coffee")
    parse_mock.assert_awaited_once_with(
        "קפה",
        ["coffee"],
        "he",
        dietary_tags=[],
        previous_category=None,
        previous_dietary_tag=None,
        has_previous_context=False,
        previous_price_tier=None,
    )


def test_chat_endpoint_handles_empty_database_in_hebrew(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=[]))

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat", json={"message": "anything", "lat": 32.08, "lon": 34.78, "lang": "he"}
        )

    assert resp.status_code == 200
    assert resp.json()["reply"] == app_module.REPLIES["he"]["empty_db"]


def test_chat_endpoint_handles_any_category_surprise_me(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee", "burger"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": None,
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": True,
            }
        ),
    )
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[None]))
    record_stat_mock = AsyncMock()
    monkeypatch.setattr(db, "record_category_request", record_stat_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "surprise me", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert "Surprise" in body["reply"]
    assert body["category"] is None
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, tag=None, price=None)
    record_stat_mock.assert_awaited_once_with(db.ANY_CATEGORY_KEY)


def test_chat_endpoint_handles_empty_database(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=[]))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "anything", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    assert "empty" in resp.json()["reply"].lower()


def test_resolve_location_endpoint_returns_coords_for_maps_link(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda text: ((32.0653, 34.7739), None))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "https://maps.app.goo.gl/abc"})

    assert resp.status_code == 200
    assert resp.json() == {"lat": 32.0653, "lon": 34.7739, "label": None}


def test_resolve_location_endpoint_falls_back_to_geocoding_a_plain_address(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda text: (None, None))
    monkeypatch.setattr(location, "geocode_address", lambda text: (32.0627450, 34.7704470))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "Rothschild 12"})

    assert resp.status_code == 200
    assert resp.json() == {"lat": 32.0627450, "lon": 34.7704470, "label": None}


def test_resolve_location_endpoint_returns_nulls_when_unresolved(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda text: (None, None))
    monkeypatch.setattr(location, "geocode_address", lambda text: None)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "not a link"})

    assert resp.status_code == 200
    assert resp.json() == {"lat": None, "lon": None}


def test_resolve_location_endpoint_returns_503_when_geocoding_is_unavailable(monkeypatch):
    # "Couldn't look it up right now" must not look like "no such address" -
    # the frontend shows its "try again" copy for any non-OK response.
    def unavailable(text):
        raise location.GeocodingUnavailable("down")

    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda text: (None, None))
    monkeypatch.setattr(location, "geocode_address", unavailable)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "Rothschild 12"})

    assert resp.status_code == 503


def test_chat_endpoint_rate_limits_after_too_many_requests(monkeypatch):
    from backend.app import limiter

    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
            }
        ),
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    limiter.enabled = True
    try:
        with TestClient(app_module.app) as client:
            responses = [
                client.post("/api/chat", json={"message": "coffee", "lat": 32.08, "lon": 34.78})
                for _ in range(21)
            ]
    finally:
        limiter.enabled = False
        limiter.reset()

    assert [r.status_code for r in responses[:20]] == [200] * 20
    assert responses[20].status_code == 429


def test_chat_endpoint_does_not_wait_on_routing_for_the_results(monkeypatch):
    # Results first: a slow or failing routing service must not be able to
    # delay (or break) the reply. Chat never calls it; /api/etas does.
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
            }
        ),
    )
    place_2 = SAMPLE_PLACE.model_copy(update={"name": "Other Cafe", "distance": 900})
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE, place_2]))
    eta_mock = AsyncMock(side_effect=AssertionError("chat must not call routing"))
    monkeypatch.setattr(routing, "get_eta_seconds_batch", eta_mock)
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "coffee", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    eta_mock.assert_not_awaited()
    body = resp.json()
    assert [p["name"] for p in body["places"]] == ["Cafelix", "Other Cafe"]
    assert [p["eta"] for p in body["places"]] == [None, None]
    # The coordinates the client needs to ask for them are on every place.
    assert all(isinstance(p["lat"], float) and isinstance(p["lon"], float) for p in body["places"])


def test_chat_followup_and_more_places_do_not_call_routing_either(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": None,
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
            }
        ),
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    eta_mock = AsyncMock(side_effect=AssertionError("must not call routing"))
    monkeypatch.setattr(routing, "get_eta_seconds_batch", eta_mock)
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        follow = client.post(
            "/api/chat",
            json={
                "message": "something else",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_offset": 3,
                "has_previous_context": True,
            },
        )
        more = client.post(
            "/api/more-places", json={"category": "coffee", "lat": 32.08, "lon": 34.78, "offset": 3}
        )

    assert follow.status_code == 200 and more.status_code == 200
    assert follow.json()["places"][0]["eta"] is None
    assert more.json()["places"][0]["eta"] is None
    eta_mock.assert_not_awaited()


def test_more_places_endpoint_passes_offset_through_to_find_nearest(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/more-places", json={"category": "coffee", "lat": 32.08, "lon": 34.78, "offset": 3}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["places"][0]["name"] == "Cafelix"
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, offset=3, tag=None, price=None)


def test_more_places_endpoint_supports_any_category_with_null_category(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/more-places", json={"category": None, "lat": 32.08, "lon": 34.78, "offset": 3})

    assert resp.status_code == 200
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, offset=3, tag=None, price=None)


def test_more_places_endpoint_passes_tag_through_to_find_nearest(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/more-places",
            json={"category": "burger", "tag": "vegan", "lat": 32.08, "lon": 34.78, "offset": 3},
        )

    assert resp.status_code == 200
    find_nearest_mock.assert_awaited_once_with("burger", 32.08, 34.78, limit=3, offset=3, tag="vegan", price=None)


def test_service_worker_is_served_from_the_root_path_not_under_static(monkeypatch):
    # Deliberately not /static/sw.js - a service worker's default scope is its
    # own directory, and it must cover the manifest's start_url ("/") to be
    # installable.
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.get("/sw.js")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/javascript"


def test_more_places_endpoint_returns_empty_list_when_no_more_matches(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[]))

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/more-places", json={"category": "coffee", "lat": 32.08, "lon": 34.78, "offset": 9}
        )

    assert resp.status_code == 200
    assert resp.json() == {"places": []}


def test_chat_endpoint_treats_a_followup_as_continuing_the_previous_category(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "burger",  # what this turn's text alone would match - should be ignored
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
                "price_tier": None,
            }
        ),
    )
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    record_stat_mock = AsyncMock()
    monkeypatch.setattr(db, "record_category_request", record_stat_mock)

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "something else",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_offset": 3,
                "has_previous_context": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "coffee"
    assert "coffee" in body["reply"]
    assert body["offset"] == 4
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, offset=3, tag=None, price=None)
    record_stat_mock.assert_awaited_once_with("coffee")


def test_chat_endpoint_followup_continues_any_category_when_previous_was_surprise_me(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={"category": None, "clarifying_question": None, "any_category": False, "is_followup": True, "price_tier": None}
        ),
    )
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    record_stat_mock = AsyncMock()
    monkeypatch.setattr(db, "record_category_request", record_stat_mock)

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "another one",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": None,
                "previous_offset": 3,
                "has_previous_context": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] is None
    assert "Surprise" in body["reply"]
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, offset=3, tag=None, price=None)
    record_stat_mock.assert_awaited_once_with(db.ANY_CATEGORY_KEY)


def test_chat_endpoint_followup_replies_gracefully_when_pagination_exhausted(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={"category": "coffee", "clarifying_question": None, "any_category": False, "is_followup": True, "price_tier": None}
        ),
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "something else",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_offset": 9,
                "has_previous_context": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == app_module.REPLIES["en"]["no_more_matches"].format(label="coffee")
    assert body["places"] == []


def test_chat_endpoint_no_more_matches_mentions_dietary_tag_when_present(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": "vegan",
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
                "price_tier": None,
            }
        ),
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "something else",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_dietary_tag": "vegan",
                "previous_offset": 1,
                "has_previous_context": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == app_module.REPLIES["en"]["no_more_matches_with_tag"].format(
        label="coffee", tag="vegan"
    )


def test_chat_endpoint_ignores_followup_flag_when_no_previous_context_given(monkeypatch):
    # Guards against relying on the LLM alone: even if it somehow returns
    # is_followup=true, there's no previous_category to fall back to when
    # has_previous_context is false, so this must run the normal fresh flow.
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
                "price_tier": None,
            }
        ),
    )
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "coffee", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, tag=None, price=None)


def test_chat_endpoint_fresh_match_includes_offset_for_future_followups(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
                "is_followup": False,
            }
        ),
    )
    place_2 = SAMPLE_PLACE.model_copy(update={"name": "Other Cafe", "distance": 900})
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE, place_2]))
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300, 400]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "coffee", "lat": 32.08, "lon": 34.78})

    assert resp.json()["offset"] == 2


def test_chat_endpoint_filters_by_dietary_tag_and_mentions_it_in_the_reply(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["burger"]))
    monkeypatch.setattr(db, "get_dietary_tags", AsyncMock(return_value=["vegan", "kosher"]))
    parse_mock = AsyncMock(
        return_value={
            "category": "burger",
            "dietary_tag": "vegan",
            "price_tier": None,
            "clarifying_question": None,
            "any_category": False,
        }
    )
    monkeypatch.setattr(llm, "parse_food_request", parse_mock)
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "vegan burger", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert body["dietary_tag"] == "vegan"
    assert "vegan" in body["reply"]
    assert "burger" in body["reply"]
    find_nearest_mock.assert_awaited_once_with("burger", 32.08, 34.78, limit=3, tag="vegan", price=None)
    parse_mock.assert_awaited_once_with(
        "vegan burger",
        ["burger"],
        "en",
        dietary_tags=["vegan", "kosher"],
        previous_category=None,
        previous_dietary_tag=None,
        has_previous_context=False,
        previous_price_tier=None,
    )


def test_chat_endpoint_any_category_with_dietary_tag_mentions_tag_in_reply(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["burger", "coffee"]))
    monkeypatch.setattr(db, "get_dietary_tags", AsyncMock(return_value=["kosher"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": None,
                "dietary_tag": "kosher",
                "price_tier": None,
                "clarifying_question": None,
                "any_category": True,
            }
        ),
    )
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "anything kosher", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] is None
    assert body["dietary_tag"] == "kosher"
    assert "kosher" in body["reply"]
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, tag="kosher", price=None)


def test_chat_endpoint_followup_continues_with_previous_dietary_tag(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["burger"]))
    monkeypatch.setattr(db, "get_dietary_tags", AsyncMock(return_value=["vegan"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": None,
                "dietary_tag": None,
                "price_tier": None,
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
                "price_tier": None,
            }
        ),
    )
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "something else",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "burger",
                "previous_dietary_tag": "vegan",
                "previous_offset": 3,
                "has_previous_context": True,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["dietary_tag"] == "vegan"
    find_nearest_mock.assert_awaited_once_with("burger", 32.08, 34.78, limit=3, offset=3, tag="vegan", price=None)


SAMPLE_USER = User(
    google_sub="g-123",
    email="a@example.com",
    name="A Name",
    picture_url="https://example.com/p.jpg",
    token_version=0,
    created_at=datetime.now(timezone.utc),
)


def test_auth_config_returns_the_google_client_id(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", "some-client-id.apps.googleusercontent.com")

    with TestClient(app_module.app) as client:
        resp = client.get("/api/auth/config")

    assert resp.status_code == 200
    assert resp.json() == {"google_client_id": "some-client-id.apps.googleusercontent.com"}


def test_auth_google_creates_a_new_user_and_sets_refresh_cookie(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(
        auth, "verify_google_id_token", lambda credential: {"sub": "g-123", "email": "a@example.com", "name": "A Name", "picture": "https://example.com/p.jpg"}
    )
    monkeypatch.setattr(db, "get_user_by_google_sub", AsyncMock(return_value=None))
    create_user_mock = AsyncMock(return_value=("user-id-1", SAMPLE_USER))
    monkeypatch.setattr(db, "create_user", create_user_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/google", json={"credential": "fake-google-token"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user"] == {"name": "A Name", "email": "a@example.com", "picture_url": "https://example.com/p.jpg"}
    assert "refresh_token" in resp.cookies
    create_user_mock.assert_awaited_once_with(
        google_sub="g-123", email="a@example.com", name="A Name", picture_url="https://example.com/p.jpg"
    )


def test_auth_google_reuses_an_existing_user_without_creating_a_new_one(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "verify_google_id_token", lambda credential: {"sub": "g-123", "email": "a@example.com", "name": "A Name", "picture": None})
    monkeypatch.setattr(db, "get_user_by_google_sub", AsyncMock(return_value=("user-id-1", SAMPLE_USER)))
    create_user_mock = AsyncMock()
    monkeypatch.setattr(db, "create_user", create_user_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/google", json={"credential": "fake-google-token"})

    assert resp.status_code == 200
    create_user_mock.assert_not_awaited()


def test_auth_google_rejects_an_invalid_credential(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "verify_google_id_token", lambda credential: None)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/google", json={"credential": "not-really-a-google-token"})

    assert resp.status_code == 401


def test_auth_refresh_issues_a_new_access_token_with_a_valid_cookie(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "decode_refresh_token", lambda token: ("user-id-1", 0))
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=SAMPLE_USER))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/refresh", cookies={"refresh_token": "some-valid-refresh-token"})

    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert "refresh_token" in resp.cookies


def test_auth_refresh_rejects_when_no_cookie_present(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/refresh")

    assert resp.status_code == 401


def test_auth_refresh_rejects_a_token_version_that_no_longer_matches(monkeypatch):
    # The user signed out (or was signed out) since this refresh token was
    # issued - db.revoke_user_sessions bumped token_version past what the
    # token itself carries.
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "decode_refresh_token", lambda token: ("user-id-1", 0))
    stale_user = SAMPLE_USER.model_copy(update={"token_version": 1})
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=stale_user))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/refresh", cookies={"refresh_token": "an-old-refresh-token"})

    assert resp.status_code == 401


def test_auth_logout_revokes_sessions_and_clears_cookie(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "decode_refresh_token", lambda token: ("user-id-1", 0))
    revoke_mock = AsyncMock()
    monkeypatch.setattr(db, "revoke_user_sessions", revoke_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/logout", cookies={"refresh_token": "some-refresh-token"})

    assert resp.status_code == 200
    revoke_mock.assert_awaited_once_with("user-id-1")


def test_auth_logout_is_a_no_op_without_a_cookie(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/auth/logout")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_auth_me_returns_the_user_for_a_valid_bearer_token(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "decode_access_token", lambda token: "user-id-1")
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=SAMPLE_USER))

    with TestClient(app_module.app) as client:
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer some-access-token"})

    assert resp.status_code == 200
    assert resp.json() == {"name": "A Name", "email": "a@example.com", "picture_url": "https://example.com/p.jpg"}


def test_auth_me_rejects_a_missing_authorization_header(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.get("/api/auth/me")

    assert resp.status_code == 401


def test_auth_me_rejects_an_invalid_access_token(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "decode_access_token", lambda token: None)

    with TestClient(app_module.app) as client:
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})

    assert resp.status_code == 401


def test_format_place_returns_lat_and_lon_not_swapped():
    # GeoJSON stores [lon, lat]; SAMPLE_PLACE is lon=34.77, lat=32.06 (Tel Aviv).
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["lat"] == 32.06
    assert formatted["lon"] == 34.77


def test_csp_allows_osm_tiles_in_img_src_only(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "ping_database", AsyncMock(return_value=True))
    with TestClient(app_module.app) as client:
        csp = client.get("/health").headers["Content-Security-Policy"]
    directives = {d.split()[0]: d.split()[1:] for d in csp.split("; ") if d}
    assert "https://tile.openstreetmap.org" in directives["img-src"]
    # Tiles are <img> loads - nothing else may have been loosened for them.
    for name, sources in directives.items():
        if name != "img-src":
            assert not any("openstreetmap" in s for s in sources)


def _price_extraction(**overrides):
    base = {
        "category": "coffee",
        "dietary_tag": None,
        "price_tier": "$",
        "clarifying_question": None,
        "any_category": False,
        "is_followup": False,
    }
    return {**base, **overrides}


def _mock_price_chat(monkeypatch, extraction, found=None):
    """The mocks every price test needs; returns the find_nearest mock."""
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(llm, "parse_food_request", AsyncMock(return_value=extraction))
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE] if found is None else found)
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))
    monkeypatch.setattr(db, "record_category_request", AsyncMock())
    return find_nearest_mock


def test_chat_endpoint_filters_by_price_and_says_so_in_the_reply(monkeypatch):
    find_nearest_mock = _mock_price_chat(monkeypatch, _price_extraction())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "cheap coffee", "lat": 32.08, "lon": 34.78})

    body = resp.json()
    assert body["reply"] == "Here are the closest cheap coffee spots:"
    assert body["price_tier"] == "$"
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, tag=None, price="$")


def test_chat_endpoint_price_and_tag_combine_in_one_phrase(monkeypatch):
    _mock_price_chat(monkeypatch, _price_extraction(dietary_tag="vegan", price_tier="$$"))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "x", "lat": 32.08, "lon": 34.78})

    assert resp.json()["reply"] == "Here are the closest mid-range vegan coffee spots:"


def test_chat_endpoint_price_only_request_searches_any_category(monkeypatch):
    find_nearest_mock = _mock_price_chat(
        monkeypatch, _price_extraction(category=None, any_category=True, price_tier="$$$")
    )

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "somewhere fancy", "lat": 32.08, "lon": 34.78})

    assert resp.json()["reply"] == "Here are the closest high-end spots overall:"
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, tag=None, price="$$$")


def test_chat_endpoint_no_matches_reply_names_the_price(monkeypatch):
    _mock_price_chat(monkeypatch, _price_extraction(price_tier="$$$"), found=[])

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "x", "lat": 32.08, "lon": 34.78})

    body = resp.json()
    assert body["reply"] == "I don't have any high-end coffee spots saved yet."
    assert body["price_tier"] == "$$$"


def test_chat_endpoint_hebrew_reply_includes_the_price_word(monkeypatch):
    _mock_price_chat(monkeypatch, _price_extraction(dietary_tag="vegan"))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "x", "lat": 32.08, "lon": 34.78, "lang": "he"})

    assert resp.json()["reply"] == "הנה המקומות הכי קרובים מסוג coffee (זול, vegan):"


def test_chat_endpoint_followup_keeps_the_previous_price_and_offset(monkeypatch):
    find_nearest_mock = _mock_price_chat(
        monkeypatch, _price_extraction(category=None, price_tier=None, is_followup=True)
    )

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "something else",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_price_tier": "$",
                "previous_offset": 3,
                "has_previous_context": True,
            },
        )

    body = resp.json()
    assert body["price_tier"] == "$"
    assert body["offset"] == 4
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, offset=3, tag=None, price="$")


def test_chat_endpoint_followup_that_changes_price_restarts_from_the_top(monkeypatch):
    # "cheaper" after two pages of $$ coffee: the new price is a different
    # result set, so the old offset (6) must not be applied to it.
    find_nearest_mock = _mock_price_chat(
        monkeypatch, _price_extraction(category=None, price_tier="$", is_followup=True)
    )

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "cheaper",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_price_tier": "$$",
                "previous_offset": 6,
                "has_previous_context": True,
            },
        )

    body = resp.json()
    assert body["category"] == "coffee"
    assert body["price_tier"] == "$"
    assert body["offset"] == 1
    assert body["reply"] == "Here are the closest cheap coffee spots:"
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, offset=0, tag=None, price="$")


def test_chat_endpoint_followup_with_new_price_and_no_results_is_not_called_exhausted(monkeypatch):
    # Nothing at the new price is "no matches", not "that's all I have" -
    # the latter would imply earlier pages of this same search existed.
    _mock_price_chat(monkeypatch, _price_extraction(category=None, price_tier="$$$", is_followup=True), found=[])

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "fancier",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_price_tier": "$",
                "previous_offset": 3,
                "has_previous_context": True,
            },
        )

    assert resp.json()["reply"] == "I don't have any high-end coffee spots saved yet."


def test_more_places_endpoint_passes_price_through_to_find_nearest(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/more-places",
            json={"category": "coffee", "price": "$$", "lat": 32.08, "lon": 34.78, "offset": 3},
        )

    assert resp.status_code == 200
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, offset=3, tag=None, price="$$")


@pytest.mark.parametrize(
    "path,extra",
    [("/api/more-places", {"price": "$$$$"}), ("/api/chat", {"previous_price_tier": "cheap"})],
)
def test_endpoints_reject_an_unknown_price_tier(monkeypatch, path, extra):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    body = {"message": "x", "category": "coffee", "lat": 32.08, "lon": 34.78, "offset": 0, **extra}

    with TestClient(app_module.app) as client:
        resp = client.post(path, json=body)

    assert resp.status_code == 422


# --- saved addresses + account deletion ----------------------------------

_AUTH = {"Authorization": "Bearer some-access-token"}


def _signed_in(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(auth, "decode_access_token", lambda token: "user-id-1")


def _saved_address(**overrides):
    from backend.models import SavedAddress

    base = {"id": "a1", "label": "Rothschild 12", "lat": 32.0668, "lon": 34.7701}
    return SavedAddress(**{**base, **overrides})


def test_saved_addresses_require_a_signed_in_user(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        assert client.get("/api/saved-addresses").status_code == 401
        assert client.post("/api/saved-addresses", json={"label": "x", "lat": 32.0, "lon": 34.0}).status_code == 401
        assert client.delete("/api/saved-addresses/a1").status_code == 401


def test_list_saved_addresses_returns_them_with_the_cap(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "list_saved_addresses", AsyncMock(return_value=[_saved_address()]))

    with TestClient(app_module.app) as client:
        resp = client.get("/api/saved-addresses", headers=_AUTH)

    assert resp.status_code == 200
    assert resp.json() == {
        "addresses": [{"id": "a1", "label": "Rothschild 12", "lat": 32.0668, "lon": 34.7701}],
        "max": db.MAX_SAVED_ADDRESSES,
    }


def test_list_saved_addresses_for_a_deleted_user_is_401(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "list_saved_addresses", AsyncMock(return_value=None))

    with TestClient(app_module.app) as client:
        resp = client.get("/api/saved-addresses", headers=_AUTH)

    assert resp.status_code == 401


def test_add_saved_address_creates_and_returns_201(monkeypatch):
    _signed_in(monkeypatch)
    add_mock = AsyncMock(return_value=("added", _saved_address()))
    monkeypatch.setattr(db, "add_saved_address", add_mock)

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/saved-addresses", json={"label": "Rothschild 12", "lat": 32.066812, "lon": 34.77012}, headers=_AUTH
        )

    assert resp.status_code == 201
    assert resp.json()["address"]["id"] == "a1"
    add_mock.assert_awaited_once_with("user-id-1", "Rothschild 12", 32.066812, 34.77012)


def test_add_saved_address_for_an_already_saved_spot_is_200(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "add_saved_address", AsyncMock(return_value=("exists", _saved_address())))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/saved-addresses", json={"label": "x", "lat": 32.0668, "lon": 34.7701}, headers=_AUTH)

    assert resp.status_code == 200
    assert resp.json()["address"]["id"] == "a1"


def test_add_saved_address_past_the_cap_is_409(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "add_saved_address", AsyncMock(return_value=("full", None)))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/saved-addresses", json={"label": "x", "lat": 32.0, "lon": 34.0}, headers=_AUTH)

    assert resp.status_code == 409


def test_add_saved_address_for_a_deleted_user_is_401(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "add_saved_address", AsyncMock(return_value=("no_user", None)))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/saved-addresses", json={"label": "x", "lat": 32.0, "lon": 34.0}, headers=_AUTH)

    assert resp.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"label": "x", "lat": 91, "lon": 34},
        {"label": "x", "lat": 32, "lon": 181},
        {"label": "x" * 201, "lat": 32, "lon": 34},
        {"label": "x", "lat": "north", "lon": 34},
        {"lat": 32, "lon": 34},
    ],
)
def test_add_saved_address_rejects_invalid_bodies(monkeypatch, body):
    _signed_in(monkeypatch)
    add_mock = AsyncMock()
    monkeypatch.setattr(db, "add_saved_address", add_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/saved-addresses", json=body, headers=_AUTH)

    assert resp.status_code == 422
    add_mock.assert_not_awaited()


def test_add_saved_address_ignores_a_client_supplied_name_field(monkeypatch):
    # There is deliberately no name/nickname field; an extra one in the body
    # must not reach storage under any key.
    _signed_in(monkeypatch)
    add_mock = AsyncMock(return_value=("added", _saved_address()))
    monkeypatch.setattr(db, "add_saved_address", add_mock)

    with TestClient(app_module.app) as client:
        client.post(
            "/api/saved-addresses",
            json={"label": "x", "lat": 32.0, "lon": 34.0, "name": "Home", "nickname": "Work"},
            headers=_AUTH,
        )

    assert add_mock.await_args.args == ("user-id-1", "x", 32.0, 34.0)


def test_delete_saved_address(monkeypatch):
    _signed_in(monkeypatch)
    remove_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(db, "remove_saved_address", remove_mock)

    with TestClient(app_module.app) as client:
        resp = client.delete("/api/saved-addresses/a1", headers=_AUTH)

    assert resp.status_code == 200
    remove_mock.assert_awaited_once_with("user-id-1", "a1")


def test_delete_saved_address_that_does_not_exist_is_404(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "remove_saved_address", AsyncMock(return_value=False))

    with TestClient(app_module.app) as client:
        resp = client.delete("/api/saved-addresses/nope", headers=_AUTH)

    assert resp.status_code == 404


def test_delete_account_removes_the_user_and_clears_the_cookie(monkeypatch):
    _signed_in(monkeypatch)
    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(db, "delete_user", delete_mock)

    with TestClient(app_module.app) as client:
        resp = client.delete("/api/auth/me", headers=_AUTH)

    assert resp.status_code == 200
    delete_mock.assert_awaited_once_with("user-id-1")
    cookie = resp.headers["set-cookie"]
    assert "refresh_token=" in cookie and "Max-Age=0" in cookie


def test_delete_account_cannot_be_triggered_by_the_cookie_alone(monkeypatch):
    # Authenticated by the bearer access token (not the cookie the browser
    # attaches on its own), so a cross-site request can't delete anyone.
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(db, "delete_user", delete_mock)

    with TestClient(app_module.app) as client:
        client.cookies.set("refresh_token", "whatever")
        resp = client.delete("/api/auth/me")

    assert resp.status_code == 401
    delete_mock.assert_not_awaited()


def test_delete_account_for_an_already_deleted_user_is_401(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "delete_user", AsyncMock(return_value=False))

    with TestClient(app_module.app) as client:
        resp = client.delete("/api/auth/me", headers=_AUTH)

    assert resp.status_code == 401


def test_auth_me_never_includes_saved_addresses(monkeypatch):
    _signed_in(monkeypatch)
    user = SAMPLE_USER.model_copy(update={"saved_addresses": [_saved_address()]})
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=user))

    with TestClient(app_module.app) as client:
        resp = client.get("/api/auth/me", headers=_AUTH)

    assert set(resp.json()) == {"name", "email", "picture_url"}


# --- resolve-location: links that carry a place name but no coordinates ----


def _resolve(monkeypatch, text, detail, geocode):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda t: detail)
    seen = []

    def fake_geocode(query):
        seen.append(query)
        return geocode(query)

    monkeypatch.setattr(location, "geocode_address", fake_geocode)
    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": text})
    return resp, seen


def test_resolve_location_geocodes_the_place_text_of_a_link_without_coordinates(monkeypatch):
    resp, seen = _resolve(
        monkeypatch,
        "https://maps.app.goo.gl/abc",
        (None, "Dizengoff Square, Tel Aviv-Yafo"),
        lambda q: (32.0779938, 34.7743493),
    )

    assert resp.json() == {"lat": 32.0779938, "lon": 34.7743493, "label": "Dizengoff Square, Tel Aviv-Yafo"}
    assert seen == ["Dizengoff Square, Tel Aviv-Yafo"]


def test_resolve_location_tries_candidates_until_one_hits(monkeypatch):
    place = "Meat Bar, Shlomo Ibn Gabirol St 67, Tel Aviv-Yafo, 6436214"
    hits = {"Meat Bar": (32.0793586, 34.7811393)}
    resp, seen = _resolve(monkeypatch, "https://maps.app.goo.gl/abc", (None, place), lambda q: hits.get(q))

    assert resp.json()["lat"] == 32.0793586
    # Stopped at the first hit rather than running the rest of the list.
    assert seen == ["Meat Bar, Shlomo Ibn Gabirol St 67, Tel Aviv-Yafo", "Meat Bar"]


def test_resolve_location_never_geocodes_a_raw_url(monkeypatch):
    # A link with nothing usable in it must not be handed to the address
    # geocoder as text - useless there, and a URL can hold more than a place.
    resp, seen = _resolve(
        monkeypatch, "https://example.com/some/page?token=secret", (None, None), lambda q: (32.0, 34.0)
    )

    assert resp.json() == {"lat": None, "lon": None}
    assert seen == []


def test_resolve_location_uses_a_links_place_text_as_the_label_when_coordinates_were_in_the_url(monkeypatch):
    resp, seen = _resolve(
        monkeypatch,
        "https://www.google.com/maps/place/Cafe+Xoho/@32.07,34.77,17z",
        ((32.07, 34.77), "Cafe Xoho"),
        lambda q: None,
    )

    assert resp.json() == {"lat": 32.07, "lon": 34.77, "label": "Cafe Xoho"}
    assert seen == []


def test_resolve_location_typed_text_is_geocoded_as_is_and_has_no_label(monkeypatch):
    resp, seen = _resolve(monkeypatch, "Dizengoff square", (None, None), lambda q: (32.0779938, 34.7743493))

    assert resp.json()["label"] is None
    assert seen == ["Dizengoff square"]


def test_resolve_location_link_lookup_outage_is_a_503_not_not_found(monkeypatch):
    def unavailable(query):
        raise location.GeocodingUnavailable("down")

    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda t: (None, "Dizengoff Square"))
    monkeypatch.setattr(location, "geocode_address", unavailable)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "https://maps.app.goo.gl/abc"})

    assert resp.status_code == 503


# --- resolve-location: "did you mean" suggestions + anonymous counters ------

from backend.services import streets  # noqa: E402


def _resolve_typed(monkeypatch, text, *, geocode, suggestion=None, counter=None):
    """Typed text through /api/resolve-location with the geocoder and the
    street matcher scripted. Returns (response, geocoded_queries, counter_mock)."""
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda t: (None, None))
    queries = []

    def fake_geocode(query):
        queries.append(query)
        result = geocode(query)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(location, "geocode_address", fake_geocode)
    suggest_mock = {"calls": []}

    def fake_suggest(t):
        suggest_mock["calls"].append(t)
        return suggestion

    monkeypatch.setattr(streets, "suggest_correction", fake_suggest)
    counter_mock = counter or AsyncMock()
    monkeypatch.setattr(db, "record_category_request", counter_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": text})
    return resp, queries, counter_mock, suggest_mock["calls"]


def test_resolve_location_offers_a_correction_instead_of_applying_it(monkeypatch):
    hits = {"Dizengoff 50": (32.0757, 34.7744)}
    resp, queries, counter, _ = _resolve_typed(
        monkeypatch, "dizingof 50", geocode=lambda q: hits.get(q), suggestion="Dizengoff 50"
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "lat": None,
        "lon": None,
        "suggestion": {"text": "Dizengoff 50", "lat": 32.0757, "lon": 34.7744},
    }
    assert queries == ["dizingof 50", "Dizengoff 50"]
    counter.assert_awaited_once_with(db.LOCATION_CORRECTION_OFFERED_KEY)


def test_resolve_location_does_not_suggest_a_correction_that_is_itself_not_found(monkeypatch):
    # A "fix" that geocodes nowhere would only send the person on a detour.
    resp, queries, counter, _ = _resolve_typed(
        monkeypatch, "dizingof 5000", geocode=lambda q: None, suggestion="Dizengoff 5000"
    )

    assert resp.json() == {"lat": None, "lon": None}
    assert queries == ["dizingof 5000", "Dizengoff 5000"]
    counter.assert_awaited_once_with(db.LOCATION_UNRESOLVED_KEY)


def test_resolve_location_with_no_close_street_is_plain_not_found(monkeypatch):
    resp, queries, counter, suggest_calls = _resolve_typed(
        monkeypatch, "asdkfjh", geocode=lambda q: None, suggestion=None
    )

    assert resp.json() == {"lat": None, "lon": None}
    assert suggest_calls == ["asdkfjh"]
    counter.assert_awaited_once_with(db.LOCATION_UNRESOLVED_KEY)


def test_resolve_location_does_not_consult_the_matcher_when_the_text_already_resolves(monkeypatch):
    resp, queries, counter, suggest_calls = _resolve_typed(
        monkeypatch, "Dizengoff 50", geocode=lambda q: (32.0757, 34.7744), suggestion="should not be used"
    )

    assert resp.json() == {"lat": 32.0757, "lon": 34.7744, "label": None}
    assert suggest_calls == []
    counter.assert_not_awaited()


def test_resolve_location_never_suggests_for_a_link(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link_detail", lambda t: (None, None))
    monkeypatch.setattr(location, "geocode_address", lambda q: None)
    suggest_calls = []
    monkeypatch.setattr(streets, "suggest_correction", lambda t: suggest_calls.append(t) or "x")

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "https://maps.app.goo.gl/abc"})

    assert resp.json() == {"lat": None, "lon": None}
    assert suggest_calls == []


def test_resolve_location_outage_while_checking_the_correction_is_a_503(monkeypatch):
    def geocode(query):
        return None if query == "dizingof 50" else location.GeocodingUnavailable("down")

    resp, *_ = _resolve_typed(monkeypatch, "dizingof 50", geocode=geocode, suggestion="Dizengoff 50")

    assert resp.status_code == 503


def test_resolve_location_still_answers_when_the_counter_cannot_be_written(monkeypatch):
    broken = AsyncMock(side_effect=RuntimeError("database down"))
    resp, *_ = _resolve_typed(monkeypatch, "asdkfjh", geocode=lambda q: None, counter=broken)

    assert resp.status_code == 200
    assert resp.json() == {"lat": None, "lon": None}


def test_location_counters_never_carry_the_typed_text(monkeypatch):
    resp, _, counter, _ = _resolve_typed(
        monkeypatch, "my secret street 7", geocode=lambda q: None, suggestion=None
    )

    (key,), _ = counter.await_args
    assert key == db.LOCATION_UNRESOLVED_KEY
    assert "secret" not in key


# --- /api/etas ----------------------------------------------------------------


def _etas_request(**overrides):
    body = {
        "mode": "walking",
        "lat": 32.08,
        "lon": 34.78,
        "destinations": [{"lat": 32.07, "lon": 34.77}, {"lat": 32.09, "lon": 34.79}],
    }
    return {**body, **overrides}


def test_etas_endpoint_returns_formatted_durations_aligned_with_the_destinations(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    eta_mock = AsyncMock(return_value=[120, 4000])
    monkeypatch.setattr(routing, "get_eta_seconds_batch", eta_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/etas", json=_etas_request(mode="driving"))

    assert resp.status_code == 200
    assert resp.json() == {"etas": ["2 min", "1h 7min"]}
    eta_mock.assert_awaited_once_with("driving", (32.08, 34.78), [(32.07, 34.77), (32.09, 34.79)])


def test_etas_endpoint_defaults_to_walking(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    eta_mock = AsyncMock(return_value=[60])
    monkeypatch.setattr(routing, "get_eta_seconds_batch", eta_mock)
    body = _etas_request(destinations=[{"lat": 32.07, "lon": 34.77}])
    del body["mode"]

    with TestClient(app_module.app) as client:
        resp = client.post("/api/etas", json=body)

    assert resp.status_code == 200
    assert eta_mock.await_args.args[0] == "walking"


def test_etas_endpoint_reports_unavailable_destinations_as_null(monkeypatch):
    # Unreachable, or routing is down/backing off: the card keeps showing
    # distance only, exactly as before this endpoint existed.
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[None, 300]))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/etas", json=_etas_request())

    assert resp.status_code == 200
    assert resp.json() == {"etas": [None, "5 min"]}


@pytest.mark.parametrize(
    "overrides",
    [
        {"destinations": []},
        {"destinations": [{"lat": 32.0, "lon": 34.0}] * 11},
        {"destinations": [{"lat": 95, "lon": 34}]},
        {"destinations": [{"lat": 32, "lon": 190}]},
        {"destinations": [{"lat": "north", "lon": 34}]},
        {"lat": 91},
        {"mode": "flying"},
    ],
    ids=["none", "too-many", "bad-dest-lat", "bad-dest-lon", "non-numeric", "bad-origin", "bad-mode"],
)
def test_etas_endpoint_rejects_invalid_requests(monkeypatch, overrides):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    eta_mock = AsyncMock()
    monkeypatch.setattr(routing, "get_eta_seconds_batch", eta_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/etas", json=_etas_request(**overrides))

    assert resp.status_code == 422
    eta_mock.assert_not_awaited()


def test_etas_endpoint_never_echoes_coordinates_back(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[60, 60]))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/etas", json=_etas_request())

    assert set(resp.json()) == {"etas"}


# --- favorites endpoints -----------------------------------------------------


def test_format_place_includes_the_place_id():
    place = SAMPLE_PLACE.model_copy(update={"id": "64b0000000000000000000a1"})
    assert format_place(place)["id"] == "64b0000000000000000000a1"


def test_favorites_endpoints_require_a_signed_in_user(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        assert client.get("/api/favorites?lat=32&lon=34").status_code == 401
        assert client.post("/api/favorites", json={"place_id": "x"}).status_code == 401
        assert client.delete("/api/favorites/x").status_code == 401


def test_favorite_places_come_back_as_ordinary_cards_for_the_given_location(monkeypatch):
    _signed_in(monkeypatch)
    place = SAMPLE_PLACE.model_copy(update={"id": "64b0000000000000000000a1", "distance": 420})
    find_mock = AsyncMock(return_value=[place])
    monkeypatch.setattr(db, "find_favorite_places", find_mock)

    with TestClient(app_module.app) as client:
        resp = client.get("/api/favorites?lat=32.07&lon=34.77", headers=_AUTH)

    assert resp.status_code == 200
    body = resp.json()["places"]
    assert body[0]["id"] == "64b0000000000000000000a1"
    assert body[0]["name"] == "Cafelix"
    assert body[0]["distance"] == "0.42 km"
    assert body[0]["eta"] is None  # filled in by /api/etas like every other card
    find_mock.assert_awaited_once_with("user-id-1", 32.07, 34.77)


def test_favorite_places_without_a_location_is_just_the_list(monkeypatch):
    _signed_in(monkeypatch)
    place = SAMPLE_PLACE.model_copy(update={"id": "64b0000000000000000000a1"})
    find_mock = AsyncMock(return_value=[place])
    monkeypatch.setattr(db, "find_favorite_places", find_mock)

    with TestClient(app_module.app) as client:
        resp = client.get("/api/favorites", headers=_AUTH)

    assert resp.status_code == 200
    assert resp.json()["places"][0]["id"] == "64b0000000000000000000a1"
    find_mock.assert_awaited_once_with("user-id-1", None, None)


@pytest.mark.parametrize("query", ["?lat=32", "?lon=34", "?lat=abc&lon=34", "?lat=95&lon=34", "?lat=32&lon=190"])
def test_favorite_places_rejects_a_partial_or_invalid_location(monkeypatch, query):
    _signed_in(monkeypatch)
    find_mock = AsyncMock()
    monkeypatch.setattr(db, "find_favorite_places", find_mock)

    with TestClient(app_module.app) as client:
        resp = client.get(f"/api/favorites{query}", headers=_AUTH)

    assert resp.status_code == 422
    find_mock.assert_not_awaited()


def test_add_favorite_statuses(monkeypatch):
    _signed_in(monkeypatch)
    cases = [("added", 201), ("exists", 200), ("full", 409), ("no_place", 404), ("no_user", 401)]

    for status, expected in cases:
        monkeypatch.setattr(db, "add_favorite", AsyncMock(return_value=status))
        with TestClient(app_module.app) as client:
            resp = client.post("/api/favorites", json={"place_id": "64b0000000000000000000a1"}, headers=_AUTH)
        assert resp.status_code == expected, status


def test_add_favorite_passes_the_user_and_place_through(monkeypatch):
    _signed_in(monkeypatch)
    add_mock = AsyncMock(return_value="added")
    monkeypatch.setattr(db, "add_favorite", add_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/favorites", json={"place_id": "64b0000000000000000000a1"}, headers=_AUTH)

    assert resp.json() == {"id": "64b0000000000000000000a1"}
    add_mock.assert_awaited_once_with("user-id-1", "64b0000000000000000000a1")


@pytest.mark.parametrize("body", [{}, {"place_id": ""}, {"place_id": "x" * 65}, {"place_id": 5}])
def test_add_favorite_rejects_invalid_bodies(monkeypatch, body):
    _signed_in(monkeypatch)
    add_mock = AsyncMock()
    monkeypatch.setattr(db, "add_favorite", add_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/favorites", json=body, headers=_AUTH)

    assert resp.status_code == 422
    add_mock.assert_not_awaited()


def test_remove_favorite(monkeypatch):
    _signed_in(monkeypatch)
    remove_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(db, "remove_favorite", remove_mock)

    with TestClient(app_module.app) as client:
        resp = client.delete("/api/favorites/64b0000000000000000000a1", headers=_AUTH)

    assert resp.status_code == 200
    remove_mock.assert_awaited_once_with("user-id-1", "64b0000000000000000000a1")


def test_remove_favorite_that_was_not_saved_is_404(monkeypatch):
    _signed_in(monkeypatch)
    monkeypatch.setattr(db, "remove_favorite", AsyncMock(return_value=False))

    with TestClient(app_module.app) as client:
        resp = client.delete("/api/favorites/64b0000000000000000000a1", headers=_AUTH)

    assert resp.status_code == 404


# --- place reports endpoint ----------------------------------------------------


def test_place_report_is_open_to_signed_out_visitors_and_stores_no_identity(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    record_mock = AsyncMock(return_value="recorded")
    monkeypatch.setattr(db, "record_place_report", record_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/place-reports", json={"place_id": "64b0000000000000000000a1", "kind": "closed"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    record_mock.assert_awaited_once_with("64b0000000000000000000a1", "closed")


def test_i_would_go_back_is_accepted_the_same_anonymous_way(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    record_mock = AsyncMock(return_value="recorded")
    monkeypatch.setattr(db, "record_place_report", record_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/place-reports", json={"place_id": "64b0000000000000000000a1", "kind": "would_return"})

    assert resp.status_code == 200
    record_mock.assert_awaited_once_with("64b0000000000000000000a1", "would_return")


def test_place_report_for_an_unknown_place_is_404(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "record_place_report", AsyncMock(return_value="no_place"))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/place-reports", json={"place_id": "64b0000000000000000000a1", "kind": "wrong_category"})

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"place_id": "64b0000000000000000000a1"},
        {"place_id": "64b0000000000000000000a1", "kind": "spam"},
        {"place_id": "", "kind": "closed"},
        {"place_id": "x" * 65, "kind": "closed"},
        {"place_id": 5, "kind": "closed"},
    ],
)
def test_place_report_rejects_invalid_bodies(monkeypatch, body):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    record_mock = AsyncMock()
    monkeypatch.setattr(db, "record_place_report", record_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/place-reports", json=body)

    assert resp.status_code == 422
    record_mock.assert_not_awaited()


# --- static pages --------------------------------------------------------------


@pytest.mark.parametrize("path,marker", [("/about", "About TLV Bot"), ("/privacy", "Privacy Policy")])
def test_static_pages_are_served_at_clean_urls(monkeypatch, path, marker):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.get(path)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert marker in resp.text


def test_standalone_pages_follow_the_apps_theme_choice():
    """About, Privacy and 404 are static pages outside the React app, so they
    only know the visitor's light/dark choice through page-theme.js. A new page
    that forgets the script would silently follow the OS setting only."""
    from pathlib import Path

    public = Path(__file__).resolve().parent.parent / "frontend" / "public"
    for page in ("about.html", "privacy.html", "404.html"):
        assert '<script src="/static/page-theme.js"></script>' in (public / page).read_text(encoding="utf-8"), page

    script = (public / "page-theme.js").read_text(encoding="utf-8")
    assert "tlv-bot-theme" in script and "data-theme" in script

    css = (public / "pages.css").read_text(encoding="utf-8")
    assert ":root[data-theme='dark']" in css
    assert ":root:not([data-theme='light'])" in css


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/chat", {"message": "x", "lat": 999, "lon": 34.78}),
        ("/api/chat", {"message": "x", "lat": 32.08, "lon": 34.78, "previous_category": "x" * 61}),
        ("/api/chat", {"message": "x", "lat": 32.08, "lon": 34.78, "previous_dietary_tag": "x" * 61}),
        ("/api/chat", {"message": "x", "lat": 32.08, "lon": 34.78, "previous_offset": -1}),
        ("/api/chat", {"message": "x", "lat": 32.08, "lon": 34.78, "previous_offset": 1001}),
        ("/api/more-places", {"category": "coffee", "lat": 32.08, "lon": 999, "offset": 0}),
        ("/api/more-places", {"category": "coffee", "lat": 32.08, "lon": 34.78, "offset": -3}),
        ("/api/more-places", {"category": "coffee", "lat": 32.08, "lon": 34.78, "offset": 10**9}),
        ("/api/more-places", {"category": "x" * 61, "lat": 32.08, "lon": 34.78, "offset": 0}),
        ("/api/more-places", {"tag": "x" * 61, "lat": 32.08, "lon": 34.78, "offset": 0}),
    ],
)
def test_chat_and_more_places_reject_out_of_range_or_oversized_fields(monkeypatch, path, body):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post(path, json=body)

    assert resp.status_code == 422


def test_resolve_location_is_rate_limited():
    """The limiter is switched off for the whole suite, so check the decorator
    is there: every other public POST has one, and this one used to be the
    exception (it opens pasted links and calls the free address lookup)."""
    route = next(r for r in app_module.app.routes if getattr(r, "path", "") == "/api/resolve-location")
    limits = app_module.limiter._route_limits
    assert any("resolve_location" in key for key in limits), list(limits)
    assert route is not None


def test_privacy_page_discloses_every_service_that_receives_a_location():
    """The page promises to list who receives what; it was wrong before (the
    weather lookup went undisclosed). Each language section must name them."""
    from pathlib import Path

    page = (Path(__file__).resolve().parent.parent / "frontend" / "public" / "privacy.html").read_text(encoding="utf-8")
    english, hebrew = page.split('<section lang="he"')
    for section in (english, hebrew):
        for service in ("open-meteo.com", "routing.openstreetmap.de", "nominatim.openstreetmap.org", "tile.openstreetmap.org"):
            assert service in section, service


@pytest.mark.parametrize(
    "lang,expected",
    [
        ("en", "Sorry, I couldn't work that out just now - please try again in a moment."),
        ("he", "סליחה, לא הצלחתי להבין את זה כרגע - נסה שוב בעוד רגע."),
    ],
)
def test_chat_reports_a_failed_llm_call_instead_of_logging_an_unmatched_craving(monkeypatch, lang, expected):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee", "burger"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": None,
                "clarifying_question": "What are you craving?",
                "any_category": False,
                "is_followup": False,
                "llm_failed": True,
            }
        ),
    )
    log_unmatched_mock = AsyncMock()
    monkeypatch.setattr(db, "log_unmatched_query", log_unmatched_mock)
    record_stat_mock = AsyncMock()
    monkeypatch.setattr(db, "record_category_request", record_stat_mock)
    find_nearest_mock = AsyncMock()
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "burger", "lat": 32.08, "lon": 34.78, "lang": lang})

    assert resp.status_code == 200
    assert resp.json() == {"reply": expected, "places": []}
    log_unmatched_mock.assert_not_awaited()
    record_stat_mock.assert_awaited_once_with(db.LLM_FAILED_KEY)
    find_nearest_mock.assert_not_awaited()


def test_a_failed_llm_call_also_stops_a_followup_from_paging(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": None,
                "clarifying_question": "x",
                "any_category": False,
                "is_followup": False,
                "llm_failed": True,
            }
        ),
    )
    monkeypatch.setattr(db, "record_category_request", AsyncMock())
    monkeypatch.setattr(db, "log_unmatched_query", AsyncMock())
    find_nearest_mock = AsyncMock()
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)

    with TestClient(app_module.app) as client:
        resp = client.post(
            "/api/chat",
            json={
                "message": "something else",
                "lat": 32.08,
                "lon": 34.78,
                "previous_category": "coffee",
                "previous_offset": 3,
                "has_previous_context": True,
            },
        )

    assert resp.json()["places"] == []
    find_nearest_mock.assert_not_awaited()


def test_both_deploy_workflows_run_the_tests_before_anything_is_uploaded():
    """A failing test must stop a deploy: the test step has to sit in the build
    job, ahead of the artifact upload that the deploy job downloads."""
    from pathlib import Path

    for name in ("deploy-production.yml", "deploy-staging.yml"):
        text = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "pytest" in text, name
        assert text.index("pytest") < text.index("actions/upload-artifact"), name


def _extraction(**overrides):
    base = {
        "category": None,
        "dietary_tag": None,
        "price_tier": None,
        "clarifying_question": None,
        "any_category": True,
        "is_followup": False,
        "unsupported": None,
    }
    return {**base, **overrides}


def _chat_with(monkeypatch, extraction, lang="en", message="something vegan", log_error=None):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee", "burger"]))
    monkeypatch.setattr(llm, "parse_food_request", AsyncMock(return_value=extraction))
    log_unmatched = AsyncMock(side_effect=log_error)
    monkeypatch.setattr(db, "log_unmatched_query", log_unmatched)
    record_stat = AsyncMock()
    monkeypatch.setattr(db, "record_category_request", record_stat)
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": message, "lat": 32.08, "lon": 34.78, "lang": lang})
    return resp, log_unmatched, record_stat


def test_an_unsupported_requirement_is_named_instead_of_answering_surprise(monkeypatch):
    resp, log_unmatched, record_stat = _chat_with(monkeypatch, _extraction(unsupported="vegan"))

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "I don't have \"vegan\" marked on my list yet. Here are the closest spots overall:"
    assert "Surprise" not in body["reply"]
    assert len(body["places"]) == 1
    log_unmatched.assert_awaited_once_with("something vegan")
    record_stat.assert_awaited_once_with(db.ANY_CATEGORY_KEY)


def test_an_unsupported_requirement_with_a_category_keeps_the_category_reply(monkeypatch):
    resp, log_unmatched, record_stat = _chat_with(
        monkeypatch, _extraction(category="coffee", any_category=False, unsupported="outdoor seating")
    )

    assert resp.json()["reply"] == "I don't have \"outdoor seating\" marked on my list yet. Here are the closest coffee spots:"
    log_unmatched.assert_awaited_once()
    record_stat.assert_awaited_once_with("coffee")


def test_the_hebrew_note_and_reply(monkeypatch):
    resp, _, _ = _chat_with(monkeypatch, _extraction(unsupported="טבעוני"), lang="he", message="משהו טבעוני")

    assert resp.json()["reply"] == 'עדיין אין לי סימון של "טבעוני" ברשימה. הנה המקומות הכי קרובים בסך הכל:'


def test_surprise_me_without_a_requirement_is_unchanged(monkeypatch):
    resp, log_unmatched, _ = _chat_with(monkeypatch, _extraction(), message="surprise me")

    assert resp.json()["reply"] == "Surprise! Here are the closest spots overall:"
    log_unmatched.assert_not_awaited()


def test_a_known_tag_with_a_requirement_reads_naturally(monkeypatch):
    resp, _, _ = _chat_with(monkeypatch, _extraction(dietary_tag="kosher", unsupported="open now"))

    assert resp.json()["reply"] == "I don't have \"open now\" marked on my list yet. Here are the closest kosher spots overall:"


def test_a_logging_failure_never_costs_the_visitor_their_answer(monkeypatch):
    resp, log_unmatched, _ = _chat_with(
        monkeypatch, _extraction(unsupported="vegan"), log_error=RuntimeError("db down")
    )

    assert resp.status_code == 200
    assert len(resp.json()["places"]) == 1
    log_unmatched.assert_awaited_once()


def test_privacy_page_says_requests_it_could_not_fully_match_are_kept():
    from pathlib import Path

    page = (Path(__file__).resolve().parent.parent / "frontend" / "public" / "privacy.html").read_text(encoding="utf-8")
    english, hebrew = page.split('<section lang="he"')
    assert "couldn't fully match" in english
    assert "לא הצלחתי להתאים במלואן" in hebrew


def test_api_requests_feed_the_client_ip_diagnostic_but_static_pages_do_not(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    seen = []
    monkeypatch.setattr(app_module.clientip, "observe", lambda peer, forwarded: seen.append((peer, forwarded)))

    with TestClient(app_module.app) as client:
        client.get("/api/categories", headers={"X-Forwarded-For": "203.0.113.9"})
        client.get("/privacy")

    assert seen == [("testclient", "203.0.113.9")]


def test_an_out_of_scope_request_gets_an_honest_answer_and_no_places(monkeypatch):
    resp, log_unmatched, record_stat = _chat_with(
        monkeypatch, _extraction(any_category=False, unsupported="night club", out_of_scope=True), message="a night club"
    )

    assert resp.status_code == 200
    assert resp.json() == {"reply": "My list only has food and coffee spots, so I can't help with that one.", "places": []}
    log_unmatched.assert_awaited_once_with("a night club")
    record_stat.assert_awaited_once_with(db.UNMATCHED_KEY)


def test_the_hebrew_out_of_scope_answer(monkeypatch):
    resp, _, _ = _chat_with(
        monkeypatch, _extraction(any_category=False, out_of_scope=True), lang="he", message="מועדון"
    )

    assert resp.json()["reply"] == "ברשימה שלי יש רק מקומות אוכל וקפה, אז בזה אני לא יכול לעזור."
    assert resp.json()["places"] == []


def test_a_named_place_is_said_not_silently_dropped(monkeypatch):
    resp, log_unmatched, _ = _chat_with(
        monkeypatch, _extraction(mentioned_place="Allenby"), message="tasty food near Allenby"
    )

    reply = resp.json()["reply"]
    assert reply == (
        'I search from the location you set, not from "Allenby" - change your location above to search there. '
        "Here are the closest spots overall:"
    )
    assert "Surprise" not in reply
    assert len(resp.json()["places"]) == 1
    log_unmatched.assert_not_awaited()


def test_a_named_place_with_a_category_keeps_the_category_reply(monkeypatch):
    resp, _, _ = _chat_with(
        monkeypatch, _extraction(category="coffee", any_category=False, mentioned_place="Florentin")
    )

    assert resp.json()["reply"] == (
        'I search from the location you set, not from "Florentin" - change your location above to search there. '
        "Here are the closest coffee spots:"
    )


def test_a_named_place_and_an_unsupported_requirement_are_both_said(monkeypatch):
    resp, _, _ = _chat_with(monkeypatch, _extraction(mentioned_place="Allenby", unsupported="vegan"))

    reply = resp.json()["reply"]
    assert reply.index("Allenby") < reply.index("vegan") < reply.index("Here are the closest spots overall:")


def test_the_hebrew_location_note(monkeypatch):
    resp, _, _ = _chat_with(monkeypatch, _extraction(mentioned_place="אלנבי"), lang="he", message="אוכל ליד אלנבי")

    assert resp.json()["reply"].startswith('אני מחפש מהמיקום שהגדרת ולא מ"אלנבי" - שנה את המיקום למעלה כדי לחפש שם.')
