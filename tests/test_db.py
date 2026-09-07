import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend import db
from backend.db import build_geo_pipeline, build_proximity_pipeline
from backend.models import PlaceResult


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

    results = await db.find_nearest("coffee", lat=32.08, lon=34.78, limit=3)

    assert len(results) == 1
    assert isinstance(results[0], PlaceResult)
    assert results[0].name == "Cafelix"
    assert results[0].distance == 123.4
    assert results[0].location.coordinates == (34.77, 32.06)


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
