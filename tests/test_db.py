import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend import db
from backend.db import build_geo_pipeline, build_proximity_pipeline, deprioritize_unlikely_matches
from backend.models import GeoPoint, PlaceResult
from backend.services import weather


@pytest.fixture(autouse=True)
def reset_categories_cache():
    db.invalidate_categories_cache()
    db.invalidate_dietary_tags_cache()
    yield
    db.invalidate_categories_cache()
    db.invalidate_dietary_tags_cache()


@pytest.mark.asyncio
async def test_find_nearest_parses_documents_into_place_results(monkeypatch):
    async def fake_aggregate(pipeline):
        yield {
            "name": "Cafelix",
            "category": "coffee",
            "location": {"type": "Point", "coordinates": [34.77, 32.06]},
            "instagram_url": None,
            "distance": 123.4,
        }

    fake_collection = MagicMock()
    fake_collection.aggregate = fake_aggregate
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)
    monkeypatch.setattr(weather, "is_raining_now", AsyncMock(return_value=False))

    results = await db.find_nearest("coffee", lat=32.08, lon=34.78, limit=3)

    assert len(results) == 1
    assert isinstance(results[0], PlaceResult)
    assert results[0].name == "Cafelix"
    assert results[0].distance == 123.4
    assert results[0].location.coordinates == (34.77, 32.06)


@pytest.mark.asyncio
async def test_find_nearest_checks_weather_at_the_requested_coordinates(monkeypatch):
    async def fake_aggregate(pipeline):
        return
        yield  # pragma: no cover - makes this an async generator with 0 items

    fake_collection = MagicMock()
    fake_collection.aggregate = fake_aggregate
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)
    is_raining_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(weather, "is_raining_now", is_raining_mock)

    await db.find_nearest("coffee", lat=32.08, lon=34.78, limit=3)

    is_raining_mock.assert_awaited_once_with(32.08, 34.78)


def test_geo_pipeline_uses_geojson_lon_lat_order():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3)
    near = pipeline[0]["$geoNear"]["near"]
    assert near["type"] == "Point"
    assert near["coordinates"] == [34.78, 32.08]


def test_geo_pipeline_filters_by_category():
    pipeline = build_geo_pipeline("burger", lat=32.08, lon=34.78, limit=3)
    assert pipeline[0]["$geoNear"]["query"] == {"category": "burger"}


def test_geo_pipeline_has_no_filter_when_category_is_none():
    pipeline = build_geo_pipeline(None, lat=32.08, lon=34.78, limit=3)
    assert pipeline[0]["$geoNear"]["query"] == {}


def test_geo_pipeline_respects_limit():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=5)
    assert pipeline[1] == {"$limit": 5}


def test_geo_pipeline_has_no_skip_stage_when_offset_is_zero():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3, offset=0)
    assert {"$skip": 0} not in pipeline
    assert pipeline == [pipeline[0], {"$limit": 3}]


def test_geo_pipeline_skips_past_already_shown_results_for_show_more():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3, offset=3)
    assert pipeline[1] == {"$skip": 3}
    assert pipeline[2] == {"$limit": 3}


def test_geo_pipeline_is_spherical():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3)
    assert pipeline[0]["$geoNear"]["spherical"] is True


def test_geo_pipeline_filters_by_dietary_tag():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3, tag="vegan")
    assert pipeline[0]["$geoNear"]["query"] == {"category": "coffee", "dietary_tags": "vegan"}


def test_geo_pipeline_filters_by_dietary_tag_with_any_category():
    pipeline = build_geo_pipeline(None, lat=32.08, lon=34.78, limit=3, tag="kosher")
    assert pipeline[0]["$geoNear"]["query"] == {"dietary_tags": "kosher"}


def test_geo_pipeline_has_no_tag_filter_when_tag_is_none():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3)
    assert "dietary_tags" not in pipeline[0]["$geoNear"]["query"]


def test_proximity_pipeline_uses_geojson_lon_lat_order():
    pipeline = build_proximity_pipeline(lat=32.08, lon=34.78, max_meters=30)
    near = pipeline[0]["$geoNear"]["near"]
    assert near["coordinates"] == [34.78, 32.08]


def test_proximity_pipeline_sets_max_distance():
    pipeline = build_proximity_pipeline(lat=32.08, lon=34.78, max_meters=30)
    assert pipeline[0]["$geoNear"]["maxDistance"] == 30


def test_proximity_pipeline_limits_to_one():
    pipeline = build_proximity_pipeline(lat=32.08, lon=34.78, max_meters=30)
    assert pipeline[1] == {"$limit": 1}


def test_proximity_pipeline_query_defaults_to_empty():
    pipeline = build_proximity_pipeline(lat=32.08, lon=34.78, max_meters=30)
    assert pipeline[0]["$geoNear"]["query"] == {}


def test_proximity_pipeline_applies_extra_query_filter():
    pipeline = build_proximity_pipeline(lat=32.08, lon=34.78, max_meters=30, query={"foo": "bar"})
    assert pipeline[0]["$geoNear"]["query"] == {"foo": "bar"}


@pytest.mark.asyncio
async def test_ping_database_returns_true_when_mongo_responds(monkeypatch):
    fake_client = MagicMock()
    fake_client.admin.command = AsyncMock(return_value={"ok": 1})
    fake_collection = MagicMock()
    fake_collection.database.client = fake_client
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)

    assert await db.ping_database() is True
    fake_client.admin.command.assert_awaited_once_with("ping")


@pytest.mark.asyncio
async def test_ping_database_returns_false_when_mongo_raises(monkeypatch):
    fake_client = MagicMock()
    fake_client.admin.command = AsyncMock(side_effect=OSError("connection refused"))
    fake_collection = MagicMock()
    fake_collection.database.client = fake_client
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)

    assert await db.ping_database() is False


@pytest.mark.asyncio
async def test_get_categories_caches_between_calls(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.distinct = AsyncMock(return_value=["coffee", "burger"])
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)

    first = await db.get_categories()
    second = await db.get_categories()

    assert first == ["burger", "coffee"]
    assert second == ["burger", "coffee"]
    fake_collection.distinct.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_categories_refetches_after_ttl_expires(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.distinct = AsyncMock(return_value=["coffee"])
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)

    fake_time = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_time[0])

    await db.get_categories()
    fake_time[0] += db.CATEGORIES_CACHE_TTL_SECONDS + 1
    await db.get_categories()

    assert fake_collection.distinct.await_count == 2


@pytest.mark.asyncio
async def test_invalidate_categories_cache_forces_refetch(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.distinct = AsyncMock(return_value=["coffee"])
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)

    await db.get_categories()
    db.invalidate_categories_cache()
    await db.get_categories()

    assert fake_collection.distinct.await_count == 2


@pytest.mark.asyncio
async def test_get_dietary_tags_caches_between_calls(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.distinct = AsyncMock(return_value=["vegan", "kosher"])
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)

    first = await db.get_dietary_tags()
    second = await db.get_dietary_tags()

    assert first == ["kosher", "vegan"]
    assert second == ["kosher", "vegan"]
    fake_collection.distinct.assert_awaited_once_with("dietary_tags")


@pytest.mark.asyncio
async def test_invalidate_dietary_tags_cache_forces_refetch(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.distinct = AsyncMock(return_value=["vegan"])
    monkeypatch.setattr(db, "get_places_collection", lambda: fake_collection)

    await db.get_dietary_tags()
    db.invalidate_dietary_tags_cache()
    await db.get_dietary_tags()

    assert fake_collection.distinct.await_count == 2


@pytest.mark.asyncio
async def test_record_category_request_upserts_an_incrementing_counter(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.update_one = AsyncMock()
    monkeypatch.setattr(db, "get_category_stats_collection", lambda: fake_collection)

    await db.record_category_request("coffee")

    fake_collection.update_one.assert_awaited_once_with(
        {"_id": "coffee"}, {"$inc": {"count": 1}}, upsert=True
    )


@pytest.mark.asyncio
async def test_log_unmatched_query_inserts_text_and_timestamp(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.insert_one = AsyncMock()
    monkeypatch.setattr(db, "get_unmatched_queries_collection", lambda: fake_collection)

    await db.log_unmatched_query("sushi near me")

    fake_collection.insert_one.assert_awaited_once()
    (inserted,), _ = fake_collection.insert_one.call_args
    assert inserted["text"] == "sushi near me"
    assert "created_at" in inserted


@pytest.mark.asyncio
async def test_get_user_by_google_sub_returns_id_and_user(monkeypatch):
    from bson import ObjectId

    object_id = ObjectId()
    fake_collection = MagicMock()
    fake_collection.find_one = AsyncMock(
        return_value={
            "_id": object_id,
            "google_sub": "g-123",
            "email": "a@example.com",
            "name": "A",
            "picture_url": None,
            "token_version": 0,
            "created_at": datetime.now(timezone.utc),
        }
    )
    monkeypatch.setattr(db, "get_users_collection", lambda: fake_collection)

    result = await db.get_user_by_google_sub("g-123")

    assert result is not None
    user_id, user = result
    assert user_id == str(object_id)
    assert user.google_sub == "g-123"
    fake_collection.find_one.assert_awaited_once_with({"google_sub": "g-123"})


@pytest.mark.asyncio
async def test_get_user_by_google_sub_returns_none_when_not_found(monkeypatch):
    fake_collection = MagicMock()
    fake_collection.find_one = AsyncMock(return_value=None)
    monkeypatch.setattr(db, "get_users_collection", lambda: fake_collection)

    assert await db.get_user_by_google_sub("nope") is None


@pytest.mark.asyncio
async def test_get_user_by_id_returns_none_for_a_malformed_id(monkeypatch):
    # Should never blow up on a garbage id (e.g. a stale/tampered token) -
    # just report "no such user," the same as a well-formed id that's simply
    # not in the database.
    fake_collection = MagicMock()
    fake_collection.find_one = AsyncMock()
    monkeypatch.setattr(db, "get_users_collection", lambda: fake_collection)

    assert await db.get_user_by_id("not-a-real-object-id") is None
    fake_collection.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_user_inserts_and_returns_id_and_user(monkeypatch):
    from bson import ObjectId

    object_id = ObjectId()
    fake_collection = MagicMock()
    fake_collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id=object_id))
    monkeypatch.setattr(db, "get_users_collection", lambda: fake_collection)

    user_id, user = await db.create_user("g-123", "a@example.com", "A", "https://example.com/p.jpg")

    assert user_id == str(object_id)
    assert user.google_sub == "g-123"
    assert user.token_version == 0
    fake_collection.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_user_sessions_increments_token_version(monkeypatch):
    from bson import ObjectId

    object_id = ObjectId()
    fake_collection = MagicMock()
    fake_collection.update_one = AsyncMock()
    monkeypatch.setattr(db, "get_users_collection", lambda: fake_collection)

    await db.revoke_user_sessions(str(object_id))

    fake_collection.update_one.assert_awaited_once_with({"_id": object_id}, {"$inc": {"token_version": 1}})


def _place(name: str, *, closes_at_hour: int | None = None, outdoor_seating: bool = False) -> PlaceResult:
    return PlaceResult(
        name=name,
        category="coffee",
        location=GeoPoint(coordinates=(34.77, 32.06)),
        distance=100.0,
        closes_at_hour=closes_at_hour,
        outdoor_seating=outdoor_seating,
    )


def test_deprioritize_keeps_order_when_nothing_is_flagged():
    places = [_place("A"), _place("B", closes_at_hour=23), _place("C", outdoor_seating=True)]
    result = deprioritize_unlikely_matches(places, current_hour=10, is_raining=False)
    assert [p.name for p in result] == ["A", "B", "C"]


def test_deprioritize_pushes_likely_closed_place_to_the_end():
    places = [_place("Closes at 20", closes_at_hour=20), _place("Open late", closes_at_hour=23), _place("No tag")]
    result = deprioritize_unlikely_matches(places, current_hour=21, is_raining=False)
    assert [p.name for p in result] == ["Open late", "No tag", "Closes at 20"]


def test_deprioritize_until_00_is_never_treated_as_closed():
    # "#until00" means open past midnight, not "closes at hour 0".
    places = [_place("Open all night", closes_at_hour=0)]
    result = deprioritize_unlikely_matches(places, current_hour=3, is_raining=False)
    assert [p.name for p in result] == ["Open all night"]


def test_deprioritize_pushes_outdoor_seating_to_the_end_when_raining():
    places = [_place("Patio", outdoor_seating=True), _place("Indoor")]
    result = deprioritize_unlikely_matches(places, current_hour=12, is_raining=True)
    assert [p.name for p in result] == ["Indoor", "Patio"]


def test_deprioritize_does_not_flag_outdoor_seating_when_not_raining():
    places = [_place("Patio", outdoor_seating=True), _place("Indoor")]
    result = deprioritize_unlikely_matches(places, current_hour=12, is_raining=False)
    assert [p.name for p in result] == ["Patio", "Indoor"]


def test_deprioritize_never_drops_a_place_just_reorders():
    places = [_place("Closed", closes_at_hour=10), _place("Rained out", outdoor_seating=True)]
    result = deprioritize_unlikely_matches(places, current_hour=12, is_raining=True)
    assert {p.name for p in result} == {"Closed", "Rained out"}
    assert len(result) == 2
