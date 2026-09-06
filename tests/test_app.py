from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import app as app_module
import db
import llm
import location
import routing
from app import format_place

SAMPLE_PLACE = {
    "name": "Cafelix",
    "category": "coffee",
    "distance": 850,
    "instagram_url": None,
    "location": {"type": "Point", "coordinates": [34.77, 32.06]},
}


def test_format_place_shows_meters_as_km_with_two_decimals_under_1km():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["distance"] == "0.85 km"


def test_format_place_shows_one_decimal_over_1km():
    place = {**SAMPLE_PLACE, "distance": 16500}
    formatted = format_place(place, eta_seconds=None)
    assert formatted["distance"] == "16.5 km"


def test_format_place_builds_keyless_maps_deep_link():
    place = {**SAMPLE_PLACE, "instagram_url": "https://www.instagram.com/cafelix/"}
    formatted = format_place(place, eta_seconds=None)
    assert formatted["maps_url"] == "https://www.google.com/maps/dir/?api=1&destination=32.06,34.77"
    assert formatted["instagram_url"] == "https://www.instagram.com/cafelix/"


def test_format_place_includes_eta_when_available():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=600)
    assert formatted["eta"] == "10 min"


def test_format_place_eta_is_none_when_routing_failed():
    formatted = format_place(SAMPLE_PLACE, eta_seconds=None)
    assert formatted["eta"] is None


def test_chat_endpoint_returns_clarifying_question_when_llm_finds_no_match(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee", "burger"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        lambda message, categories: {
            "category": None,
            "clarifying_question": "What are you craving?",
            "any_category": False,
        },
    )

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "surprise me", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "What are you craving?"
    assert body["places"] == []


def test_chat_endpoint_returns_nearest_places_on_match(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        lambda message, categories: {
            "category": "coffee",
            "clarifying_question": None,
            "any_category": False,
        },
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    monkeypatch.setattr(routing, "get_eta_seconds", AsyncMock(return_value=300))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "flat white", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert "coffee" in body["reply"]
    assert body["places"][0]["name"] == "Cafelix"
    assert body["places"][0]["eta"] == "5 min"


def test_chat_endpoint_handles_any_category_surprise_me(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee", "burger"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        lambda message, categories: {
            "category": None,
            "clarifying_question": None,
            "any_category": True,
        },
    )
    find_nearest_mock = AsyncMock(return_value=[SAMPLE_PLACE])
    monkeypatch.setattr(db, "find_nearest", find_nearest_mock)
    monkeypatch.setattr(routing, "get_eta_seconds", AsyncMock(return_value=None))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "surprise me", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    assert "Surprise" in resp.json()["reply"]
    find_nearest_mock.assert_awaited_once_with(None, 32.08, 34.78, limit=3)


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


def test_resolve_location_endpoint_returns_nulls_when_unresolved(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(location, "resolve_maps_link", lambda text: None)

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
        lambda message, categories: {
            "category": "coffee",
            "clarifying_question": None,
            "any_category": False,
        },
    )
    monkeypatch.setattr(db, "find_nearest", AsyncMock(return_value=[SAMPLE_PLACE]))
    eta_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(routing, "get_eta_seconds", eta_mock)

    with TestClient(app_module.app) as client:
        client.post("/api/chat", json={"message": "flat white", "lat": 32.08, "lon": 34.78})

    args, _ = eta_mock.call_args
    assert args[0] == "walking"
