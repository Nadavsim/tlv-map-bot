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
async def test_ensure_indexes_sets_up_favorites_with_unique_pair_index_and_validator(monkeypatch):
    def fake_collection():
        collection = MagicMock()
        collection.create_index = AsyncMock()
        collection.index_information = AsyncMock(return_value={})
        return collection

    places, unmatched, users, favorites, place_reports = (fake_collection() for _ in range(5))
    monkeypatch.setattr(db, "get_places_collection", lambda: places)
    monkeypatch.setattr(db, "get_unmatched_queries_collection", lambda: unmatched)
    monkeypatch.setattr(db, "get_users_collection", lambda: users)
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)
    monkeypatch.setattr(db, "get_place_reports_collection", lambda: place_reports)
    validator_mock = AsyncMock()
    monkeypatch.setattr(db, "_ensure_schema_validator", validator_mock)

    await db.ensure_indexes()

    favorites.create_index.assert_awaited_once_with([("user_id", 1), ("place_id", 1)], unique=True)
    validator_mock.assert_any_await(favorites, "favorites", db.FAVORITES_JSON_SCHEMA)
    place_reports.create_index.assert_awaited_once_with([("place_id", 1), ("kind", 1)], unique=True)
    validator_mock.assert_any_await(place_reports, "place_reports", db.PLACE_REPORTS_JSON_SCHEMA)


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


def test_geo_pipeline_filters_by_price_tier():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3, price="$")
    assert pipeline[0]["$geoNear"]["query"] == {"category": "coffee", "price_tier": "$"}


def test_geo_pipeline_combines_price_and_dietary_tag_with_any_category():
    pipeline = build_geo_pipeline(None, lat=32.08, lon=34.78, limit=3, tag="date", price="$$$")
    assert pipeline[0]["$geoNear"]["query"] == {"dietary_tags": "date", "price_tier": "$$$"}


def test_geo_pipeline_has_no_price_filter_when_price_is_none():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3)
    assert "price_tier" not in pipeline[0]["$geoNear"]["query"]


# --- saved addresses -----------------------------------------------------

_SAVED_USER_ID = "64b000000000000000000001"


def _user_with(addresses):
    from backend.models import User

    return User(
        google_sub="g-1",
        email="a@example.com",
        name="A",
        saved_addresses=addresses,
        created_at=datetime.now(timezone.utc),
    )


def _saved(n, lat=32.0, lon=34.0):
    from backend.models import SavedAddress

    return SavedAddress(id=f"id{n}", label=f"Street {n}", lat=lat + n / 1000, lon=lon)


def test_normalize_label_keeps_a_typed_address():
    assert db.normalize_address_label("Rothschild 12, Tel Aviv", 32.0, 34.0) == "Rothschild 12, Tel Aviv"


def test_normalize_label_collapses_whitespace_and_truncates():
    assert db.normalize_address_label("  Dizengoff \n  50  ", 32.0, 34.0) == "Dizengoff 50"
    assert len(db.normalize_address_label("x" * 300, 32.0, 34.0)) == db.SAVED_ADDRESS_LABEL_MAX_LENGTH


@pytest.mark.parametrize(
    "text",
    [
        "https://www.google.com/maps/place/Foo/@32.07,34.77,17z?utm_source=x",
        "http://maps.app.goo.gl/abc",
        "www.example.com/somewhere",
        "maps.google.com/?q=1",
        "goo.gl/maps/abc",
        "   ",
        "",
    ],
)
def test_normalize_label_never_stores_a_link_or_empty_text(text):
    # A pasted link can carry tracking parameters or a place name; it's
    # replaced by the (rounded) coordinates instead of being kept.
    assert db.normalize_address_label(text, 32.0668, 34.77) == "32.0668, 34.7700"


@pytest.mark.asyncio
async def test_list_saved_addresses_distinguishes_missing_user_from_empty(monkeypatch):
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=None))
    assert await db.list_saved_addresses(_SAVED_USER_ID) is None

    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_user_with([])))
    assert await db.list_saved_addresses(_SAVED_USER_ID) == []


@pytest.mark.asyncio
async def test_add_saved_address_rounds_coordinates_and_pushes_with_a_cap_guard(monkeypatch):
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_user_with([])))
    users = MagicMock()
    users.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    monkeypatch.setattr(db, "get_users_collection", lambda: users)

    status, address = await db.add_saved_address(_SAVED_USER_ID, "Rothschild 12", 32.066812345, 34.770099999)

    assert status == "added"
    assert (address.lat, address.lon) == (32.0668, 34.7701)
    assert address.label == "Rothschild 12"
    assert len(address.id) == 32
    query, update = users.update_one.call_args.args
    # The cap is enforced in the filter itself, not only by the earlier read.
    assert query["saved_addresses.4"] == {"$exists": False}
    assert update == {"$push": {"saved_addresses": address.model_dump()}}


@pytest.mark.asyncio
async def test_add_saved_address_returns_the_existing_one_for_the_same_spot(monkeypatch):
    from backend.models import SavedAddress

    existing = SavedAddress(id="id1", label="Rothschild 12", lat=32.0668, lon=34.7701)
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_user_with([existing])))
    users = MagicMock()
    users.update_one = AsyncMock()
    monkeypatch.setattr(db, "get_users_collection", lambda: users)

    # Differs only below the stored precision - same spot, so no duplicate.
    status, address = await db.add_saved_address(_SAVED_USER_ID, "anything", 32.06681, 34.77009)

    assert status == "exists"
    assert address == existing
    users.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_saved_address_refuses_past_the_cap(monkeypatch):
    full = [_saved(n) for n in range(db.MAX_SAVED_ADDRESSES)]
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_user_with(full)))
    users = MagicMock()
    users.update_one = AsyncMock()
    monkeypatch.setattr(db, "get_users_collection", lambda: users)

    status, address = await db.add_saved_address(_SAVED_USER_ID, "New", 31.0, 33.0)

    assert (status, address) == ("full", None)
    users.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_saved_address_reports_full_when_a_concurrent_add_wins(monkeypatch):
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_user_with([])))
    users = MagicMock()
    users.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
    monkeypatch.setattr(db, "get_users_collection", lambda: users)

    assert await db.add_saved_address(_SAVED_USER_ID, "x", 32.0, 34.0) == ("full", None)


@pytest.mark.asyncio
async def test_add_saved_address_for_a_deleted_user(monkeypatch):
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=None))
    assert await db.add_saved_address(_SAVED_USER_ID, "x", 32.0, 34.0) == ("no_user", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("modified,expected", [(1, True), (0, False)])
async def test_remove_saved_address_pulls_by_id(monkeypatch, modified, expected):
    users = MagicMock()
    users.update_one = AsyncMock(return_value=MagicMock(modified_count=modified))
    monkeypatch.setattr(db, "get_users_collection", lambda: users)

    assert await db.remove_saved_address(_SAVED_USER_ID, "abc") is expected
    _, update = users.update_one.call_args.args
    assert update == {"$pull": {"saved_addresses": {"id": "abc"}}}


@pytest.mark.asyncio
async def test_remove_saved_address_with_a_malformed_user_id(monkeypatch):
    assert await db.remove_saved_address("not-an-object-id", "abc") is False


@pytest.mark.asyncio
async def test_delete_user_removes_favorites_before_the_account(monkeypatch):
    order = []
    favorites = MagicMock()
    favorites.delete_many = AsyncMock(side_effect=lambda *_: order.append("favorites"))
    users = MagicMock()
    users.delete_one = AsyncMock(
        side_effect=lambda *_: order.append("user") or MagicMock(deleted_count=1)
    )
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)
    monkeypatch.setattr(db, "get_users_collection", lambda: users)

    assert await db.delete_user(_SAVED_USER_ID) is True
    assert order == ["favorites", "user"]
    favorites.delete_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_user_with_a_malformed_id_touches_nothing(monkeypatch):
    favorites = MagicMock()
    favorites.delete_many = AsyncMock()
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)

    assert await db.delete_user("not-an-object-id") is False
    favorites.delete_many.assert_not_awaited()


def test_users_schema_describes_saved_addresses_without_any_name_field():
    item = db.USERS_JSON_SCHEMA["properties"]["saved_addresses"]["items"]
    assert set(item["properties"]) == {"id", "label", "lat", "lon"}


# --- favorites -----------------------------------------------------------------

_FAV_USER = "64b000000000000000000001"
_FAV_PLACE = "64b0000000000000000000a1"


class _FakeCursor:
    """Just enough of a Motor cursor: .sort() chains, async iteration."""

    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def __aiter__(self):
        async def gen():
            for doc in self._docs:
                yield doc

        return gen()


def _a_user():
    from backend.models import User

    return User(google_sub="g-1", email="a@example.com", name="A", created_at=datetime.now(timezone.utc))


def test_geo_pipeline_can_be_restricted_to_given_place_ids():
    ids = ["id-1", "id-2"]
    pipeline = build_geo_pipeline(None, lat=32.08, lon=34.78, limit=100, place_ids=ids)
    assert pipeline[0]["$geoNear"]["query"] == {"_id": {"$in": ids}}
    assert pipeline[-1] == {"$limit": 100}


def test_geo_pipeline_without_place_ids_has_no_id_filter():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3)
    assert "_id" not in pipeline[0]["$geoNear"]["query"]


def test_place_result_carries_the_documents_id_as_a_string():
    from bson import ObjectId

    oid = ObjectId()
    doc = {
        "_id": oid,
        "name": "Cafelix",
        "category": "coffee",
        "location": {"type": "Point", "coordinates": [34.78, 32.08]},
        "distance": 120.0,
    }
    assert db._place_result(doc).id == str(oid)
    assert db._place_result({k: v for k, v in doc.items() if k != "_id"}).id is None


@pytest.mark.asyncio
async def test_find_favorite_places_searches_only_the_favorited_ids_nearest_first(monkeypatch):
    from bson import ObjectId

    place_oid = ObjectId()
    favorites = MagicMock()
    favorites.find = MagicMock(return_value=_FakeCursor([{"place_id": place_oid}]))
    places = MagicMock()
    places.aggregate = MagicMock(
        return_value=_FakeCursor(
            [
                {
                    "_id": place_oid,
                    "name": "Cafelix",
                    "category": "coffee",
                    "location": {"type": "Point", "coordinates": [34.78, 32.08]},
                    "distance": 150.0,
                }
            ]
        )
    )
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)
    monkeypatch.setattr(db, "get_places_collection", lambda: places)
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_a_user()))

    results = await db.find_favorite_places(_FAV_USER, 32.07, 34.77)

    assert [r.name for r in results] == ["Cafelix"]
    assert results[0].id == str(place_oid)
    pipeline = places.aggregate.call_args.args[0]
    assert pipeline[0]["$geoNear"]["query"] == {"_id": {"$in": [place_oid]}}
    assert pipeline[0]["$geoNear"]["near"]["coordinates"] == [34.77, 32.07]


@pytest.mark.asyncio
async def test_find_favorite_places_without_a_position_still_runs_the_query(monkeypatch):
    from bson import ObjectId

    place_oid = ObjectId()
    favorites = MagicMock()
    favorites.find = MagicMock(return_value=_FakeCursor([{"place_id": place_oid}]))
    places = MagicMock()
    places.aggregate = MagicMock(return_value=_FakeCursor([]))
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)
    monkeypatch.setattr(db, "get_places_collection", lambda: places)
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_a_user()))

    await db.find_favorite_places(_FAV_USER)

    near = places.aggregate.call_args.args[0][0]["$geoNear"]["near"]["coordinates"]
    assert near == [db.FAVORITES_REFERENCE_POINT[1], db.FAVORITES_REFERENCE_POINT[0]]


@pytest.mark.asyncio
async def test_find_favorite_places_with_none_saved_does_not_query_places(monkeypatch):
    favorites = MagicMock()
    favorites.find = MagicMock(return_value=_FakeCursor([]))
    places = MagicMock()
    places.aggregate = MagicMock()
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)
    monkeypatch.setattr(db, "get_places_collection", lambda: places)
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_a_user()))

    assert await db.find_favorite_places(_FAV_USER, 32.07, 34.77) == []
    places.aggregate.assert_not_called()


@pytest.mark.asyncio
async def test_find_favorite_places_for_a_deleted_user_is_none(monkeypatch):
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=None))
    assert await db.find_favorite_places(_FAV_USER, 32.07, 34.77) is None


def _fav_collections(monkeypatch, *, place_exists=True, already=False, count=0, insert_error=None, user=True):
    monkeypatch.setattr(db, "get_user_by_id", AsyncMock(return_value=_a_user() if user else None))
    places = MagicMock()
    places.find_one = AsyncMock(return_value={"_id": "x"} if place_exists else None)
    favorites = MagicMock()
    favorites.find_one = AsyncMock(return_value={"_id": "y"} if already else None)
    favorites.count_documents = AsyncMock(return_value=count)
    favorites.insert_one = AsyncMock(side_effect=insert_error)
    monkeypatch.setattr(db, "get_places_collection", lambda: places)
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)
    return favorites


@pytest.mark.asyncio
async def test_add_favorite_inserts_a_document_with_object_ids(monkeypatch):
    from bson import ObjectId

    favorites = _fav_collections(monkeypatch)

    assert await db.add_favorite(_FAV_USER, _FAV_PLACE) == "added"
    doc = favorites.insert_one.call_args.args[0]
    assert doc["user_id"] == ObjectId(_FAV_USER) and doc["place_id"] == ObjectId(_FAV_PLACE)
    assert doc["created_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_add_favorite_is_idempotent(monkeypatch):
    favorites = _fav_collections(monkeypatch, already=True)

    assert await db.add_favorite(_FAV_USER, _FAV_PLACE) == "exists"
    favorites.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_favorite_treats_a_duplicate_key_race_as_exists(monkeypatch):
    from pymongo.errors import DuplicateKeyError

    _fav_collections(monkeypatch, insert_error=DuplicateKeyError("dup"))

    assert await db.add_favorite(_FAV_USER, _FAV_PLACE) == "exists"


@pytest.mark.asyncio
async def test_add_favorite_stops_at_the_cap(monkeypatch):
    favorites = _fav_collections(monkeypatch, count=db.MAX_FAVORITES)

    assert await db.add_favorite(_FAV_USER, _FAV_PLACE) == "full"
    favorites.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_favorite_rejects_unknown_places_users_and_malformed_ids(monkeypatch):
    favorites = _fav_collections(monkeypatch, place_exists=False)
    assert await db.add_favorite(_FAV_USER, _FAV_PLACE) == "no_place"
    assert await db.add_favorite(_FAV_USER, "not-an-object-id") == "no_place"

    favorites = _fav_collections(monkeypatch, user=False)
    assert await db.add_favorite(_FAV_USER, _FAV_PLACE) == "no_user"
    favorites.insert_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("deleted,expected", [(1, True), (0, False)])
async def test_remove_favorite(monkeypatch, deleted, expected):
    favorites = MagicMock()
    favorites.delete_one = AsyncMock(return_value=MagicMock(deleted_count=deleted))
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)

    assert await db.remove_favorite(_FAV_USER, _FAV_PLACE) is expected


@pytest.mark.asyncio
async def test_remove_favorite_with_a_malformed_id_touches_nothing(monkeypatch):
    favorites = MagicMock()
    favorites.delete_one = AsyncMock()
    monkeypatch.setattr(db, "get_favorites_collection", lambda: favorites)

    assert await db.remove_favorite(_FAV_USER, "nope") is False
    favorites.delete_one.assert_not_awaited()


# --- place reports -------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_place_report_upserts_a_counter_with_a_snapshot(monkeypatch):
    from bson import ObjectId

    place_oid = ObjectId()
    places = MagicMock()
    places.find_one = AsyncMock(return_value={"_id": place_oid, "name": "Cafelix", "category": "coffee"})
    reports = MagicMock()
    reports.update_one = AsyncMock()
    monkeypatch.setattr(db, "get_places_collection", lambda: places)
    monkeypatch.setattr(db, "get_place_reports_collection", lambda: reports)

    assert await db.record_place_report(str(place_oid), "closed") == "recorded"

    query, update = reports.update_one.call_args.args
    assert query == {"place_id": place_oid, "kind": "closed"}
    assert update["$inc"] == {"count": 1}
    assert update["$set"]["name"] == "Cafelix" and update["$set"]["category"] == "coffee"
    assert "first_at" in update["$setOnInsert"]
    assert reports.update_one.call_args.kwargs == {"upsert": True}
    # Nothing about who sent it is stored.
    stored_keys = set(update["$set"]) | set(update["$inc"]) | set(update["$setOnInsert"])
    assert stored_keys == {"count", "last_at", "name", "category", "first_at"}


@pytest.mark.asyncio
async def test_record_place_report_ignores_unknown_and_malformed_places(monkeypatch):
    places = MagicMock()
    places.find_one = AsyncMock(return_value=None)
    reports = MagicMock()
    reports.update_one = AsyncMock()
    monkeypatch.setattr(db, "get_places_collection", lambda: places)
    monkeypatch.setattr(db, "get_place_reports_collection", lambda: reports)

    assert await db.record_place_report("64b0000000000000000000a1", "closed") == "no_place"
    assert await db.record_place_report("not-an-id", "closed") == "no_place"
    reports.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,expected_query", [
    (None, {"place_id": {"$in": ["a", "b"]}}),
    ("wrong_category", {"place_id": {"$in": ["a", "b"]}, "kind": "wrong_category"}),
])
async def test_clear_place_reports(monkeypatch, kind, expected_query):
    reports = MagicMock()
    reports.delete_many = AsyncMock(return_value=MagicMock(deleted_count=2))
    monkeypatch.setattr(db, "get_place_reports_collection", lambda: reports)

    assert await db.clear_place_reports(["a", "b"], kind=kind) == 2
    reports.delete_many.assert_awaited_once_with(expected_query)


@pytest.mark.asyncio
async def test_clear_place_reports_with_nothing_to_clear_does_not_touch_the_database(monkeypatch):
    reports = MagicMock()
    reports.delete_many = AsyncMock()
    monkeypatch.setattr(db, "get_place_reports_collection", lambda: reports)

    assert await db.clear_place_reports([]) == 0
    reports.delete_many.assert_not_awaited()
