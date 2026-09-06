from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import app as app_module
import db
import llm
from app import format_place


def test_format_place_shows_meters_as_km_with_two_decimals_under_1km():
    place = {
        "name": "Cafelix",
        "category": "coffee",
        "distance": 850,
        "instagram_url": None,
        "location": {"type": "Point", "coordinates": [34.77, 32.06]},
    }
    formatted = format_place(place)
    assert formatted["distance"] == "0.85 km"


def test_format_place_shows_one_decimal_over_1km():
    place = {
        "name": "Far Away Burger",
        "category": "burger",
        "distance": 16500,
        "instagram_url": None,
        "location": {"type": "Point", "coordinates": [34.77, 32.06]},
    }
    formatted = format_place(place)
    assert formatted["distance"] == "16.5 km"


def test_format_place_builds_keyless_maps_deep_link():
    place = {
        "name": "Cafelix",
        "category": "coffee",
        "distance": 100,
        "instagram_url": "https://www.instagram.com/cafelix/",
        "location": {"type": "Point", "coordinates": [34.77, 32.06]},
    }
    formatted = format_place(place)
    assert formatted["maps_url"] == "https://www.google.com/maps/dir/?api=1&destination=32.06,34.77"
    assert formatted["instagram_url"] == "https://www.instagram.com/cafelix/"


def test_chat_endpoint_returns_clarifying_question_when_llm_finds_no_match(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=["coffee", "burger"]))
    monkeypatch.setattr(
        llm,
        "parse_food_request",
        lambda message, categories: {"category": None, "clarifying_question": "What are you craving?"},
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
        lambda message, categories: {"category": "coffee", "clarifying_question": None},
    )
    monkeypatch.setattr(
        db,
        "find_nearest",
        AsyncMock(
            return_value=[
                {
                    "name": "Cafelix",
                    "category": "coffee",
                    "distance": 500,
                    "instagram_url": None,
                    "location": {"type": "Point", "coordinates": [34.77, 32.06]},
                }
            ]
        ),
    )

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "flat white", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    body = resp.json()
    assert "coffee" in body["reply"]
    assert body["places"][0]["name"] == "Cafelix"


def test_chat_endpoint_handles_empty_database(monkeypatch):
    monkeypatch.setattr(db, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(db, "get_categories", AsyncMock(return_value=[]))

    with TestClient(app_module.app) as client:
        resp = client.post("/api/chat", json={"message": "anything", "lat": 32.08, "lon": 34.78})

    assert resp.status_code == 200
    assert "empty" in resp.json()["reply"].lower()
