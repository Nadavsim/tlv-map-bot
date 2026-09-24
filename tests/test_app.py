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
    assert body["places"][0]["eta"] == "5 min"
    assert body["category"] == "coffee"
    record_stat_mock.assert_awaited_once_with("coffee")


def test_chat_endpoint_replies_in_hebrew_when_lang_is_he(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    parse_mock = AsyncMock(
        return_value={
            "category": "coffee",
            "dietary_tag": None,
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
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, tag=None)
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
    monkeypatch.setattr(location, "resolve_maps_link", lambda text: (32.0653, 34.7739))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "https://maps.app.goo.gl/abc"})

    assert resp.status_code == 200
    assert resp.json() == {"lat": 32.0653, "lon": 34.7739}


def test_resolve_location_endpoint_falls_back_to_geocoding_a_plain_address(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link", lambda text: None)
    monkeypatch.setattr(location, "geocode_address", lambda text: (32.0627450, 34.7704470))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "Rothschild 12"})

    assert resp.status_code == 200
    assert resp.json() == {"lat": 32.0627450, "lon": 34.7704470}


def test_resolve_location_endpoint_returns_nulls_when_unresolved(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link", lambda text: None)
    monkeypatch.setattr(location, "geocode_address", lambda text: None)

    with TestClient(app_module.app) as client:
        resp = client.post("/api/resolve-location", json={"text": "not a link"})

    assert resp.status_code == 200
    assert resp.json() == {"lat": None, "lon": None}


def test_chat_endpoint_defaults_to_walking_mode(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": None,
                "clarifying_question": None,
                "any_category": False,
            }
        ),
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    eta_mock = AsyncMock(return_value=[None])
    monkeypatch.setattr(routing, "get_eta_seconds_batch", eta_mock)
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        client.post("/api/chat", json={"message": "flat white", "lat": 32.08, "lon": 34.78})

    args, _ = eta_mock.call_args
    assert args[0] == "walking"


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


def test_chat_endpoint_requests_one_batched_eta_call_for_multiple_places(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={
                "category": "coffee",
                "dietary_tag": None,
                "clarifying_question": None,
                "any_category": False,
            }
        ),
    )
    place_2 = SAMPLE_PLACE.model_copy(update={"name": "Other Cafe", "distance": 900})
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE, place_2]))
    eta_mock = AsyncMock(return_value=[120, 240])
    monkeypatch.setattr(routing, "get_eta_seconds_batch", eta_mock)
    monkeypatch.setattr(db, "record_category_request", AsyncMock())

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "coffee", "lat": 32.08, "lon": 34.78})

    eta_mock.assert_awaited_once()
    body = resp.json()
    assert body["places"][0]["eta"] == "2 min"
    assert body["places"][1]["eta"] == "4 min"


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
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, offset=3, tag=None)


def test_more_places_endpoint_supports_any_category_with_null_category(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds_batch", AsyncMock(return_value=[300]))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/more-places", json={"category": None, "lat": 32.08, "lon": 34.78, "offset": 3})

    assert resp.status_code == 200
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, offset=3, tag=None)


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
    find_nearest_mock.assert_awaited_once_with("burger", 32.08, 34.78, limit=3, offset=3, tag="vegan")


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
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, offset=3, tag=None)
    record_stat_mock.assert_awaited_once_with("coffee")


def test_chat_endpoint_followup_continues_any_category_when_previous_was_surprise_me(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={"category": None, "clarifying_question": None, "any_category": False, "is_followup": True}
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
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, offset=3, tag=None)
    record_stat_mock.assert_awaited_once_with(db.ANY_CATEGORY_KEY)


def test_chat_endpoint_followup_replies_gracefully_when_pagination_exhausted(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        AsyncMock(
            return_value={"category": "coffee", "clarifying_question": None, "any_category": False, "is_followup": True}
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
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
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
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
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
    find_nearest_mock.assert_awaited_once_with("coffee", 32.08, 34.78, limit=3, tag=None)


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
    find_nearest_mock.assert_awaited_once_with("burger", 32.08, 34.78, limit=3, tag="vegan")
    parse_mock.assert_awaited_once_with(
        "vegan burger",
        ["burger"],
        "en",
        dietary_tags=["vegan", "kosher"],
        previous_category=None,
        previous_dietary_tag=None,
        has_previous_context=False,
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
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3, tag="kosher")


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
                "clarifying_question": None,
                "any_category": False,
                "is_followup": True,
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
    find_nearest_mock.assert_awaited_once_with("burger", 32.08, 34.78, limit=3, offset=3, tag="vegan")


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
