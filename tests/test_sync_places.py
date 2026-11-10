from scripts.sync_places import looks_like_truncated_fetch


def test_no_guard_needed_when_database_was_empty():
    assert looks_like_truncated_fetch(new_count=50, existing_count=0) is False


def test_flags_a_big_drop_as_likely_truncated():
    assert looks_like_truncated_fetch(new_count=10, existing_count=160) is True


def test_does_not_flag_a_small_expected_drop():
    assert looks_like_truncated_fetch(new_count=150, existing_count=160) is False


def test_does_not_flag_growth():
    assert looks_like_truncated_fetch(new_count=200, existing_count=160) is False


def test_respects_a_custom_ratio():
    assert looks_like_truncated_fetch(new_count=140, existing_count=160, ratio=0.95) is True
    assert looks_like_truncated_fetch(new_count=140, existing_count=160, ratio=0.5) is False


def test_boundary_is_exclusive_below_ratio_not_at_it():
    # new_count exactly at the ratio threshold should not be flagged - only
    # strictly below it.
    assert looks_like_truncated_fetch(new_count=112, existing_count=160, ratio=0.7) is False


# --- reports are cleared once the map has been acted on --------------------------

import pytest
from unittest.mock import AsyncMock, MagicMock

from scripts import sync_places


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for doc in self._docs:
                yield doc

        return gen()


def _parsed_place(category, instagram_url=None):
    return {
        "name": "Cafelix",
        "category": category,
        "longitude": 34.78,
        "latitude": 32.08,
        "instagram_url": instagram_url,
        "dietary_tags": [],
        "price_tier": None,
        "closes_at_hour": None,
        "outdoor_seating": False,
    }


async def _run_sync(monkeypatch, *, stored_category, new_category, stale_ids=(), instagram_url=None, collection=None):
    collection = collection or MagicMock()
    collection.count_documents = AsyncMock(return_value=1)
    collection.update_one = AsyncMock()
    collection.insert_one = AsyncMock()
    collection.find = MagicMock(return_value=_Cursor([{"_id": i} for i in stale_ids]))
    collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=len(stale_ids)))
    clear_mock = AsyncMock(return_value=0)

    monkeypatch.setattr(sync_places, "fetch_kml", lambda: "<kml/>")
    monkeypatch.setattr(sync_places, "parse_kml_text", lambda text: [_parsed_place(new_category, instagram_url)])
    monkeypatch.setattr(sync_places, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(sync_places, "get_places_collection", lambda: collection)
    monkeypatch.setattr(
        sync_places, "find_nearby", AsyncMock(return_value={"_id": "place-1", "category": stored_category})
    )
    monkeypatch.setattr(sync_places, "invalidate_categories_cache", lambda: None)
    monkeypatch.setattr(sync_places, "clear_place_reports", clear_mock)

    await sync_places.sync()
    return clear_mock


@pytest.mark.asyncio
async def test_sync_clears_wrong_category_reports_when_the_category_changed(monkeypatch):
    clear_mock = await _run_sync(monkeypatch, stored_category="coffee", new_category="bakery")

    clear_mock.assert_awaited_once_with(["place-1"], kinds=["wrong_category"])


@pytest.mark.asyncio
async def test_sync_keeps_reports_when_nothing_changed(monkeypatch):
    clear_mock = await _run_sync(monkeypatch, stored_category="coffee", new_category="coffee")

    clear_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_clears_every_report_for_places_removed_from_the_map(monkeypatch):
    clear_mock = await _run_sync(
        monkeypatch, stored_category="coffee", new_category="coffee", stale_ids=["gone-1", "gone-2"]
    )

    clear_mock.assert_awaited_once_with(["gone-1", "gone-2"])


# --- the map's Instagram link vs one backfilled by hand ----------------------------


async def _sync_and_get_update(monkeypatch, instagram_url):
    collection = MagicMock()
    await _run_sync(
        monkeypatch, stored_category="coffee", new_category="coffee", instagram_url=instagram_url, collection=collection
    )
    return collection.update_one.await_args.args[1]["$set"]


@pytest.mark.asyncio
async def test_sync_applies_an_instagram_link_added_to_an_existing_pin(monkeypatch):
    changes = await _sync_and_get_update(monkeypatch, "https://instagram.com/cafelix")

    assert changes["instagram_url"] == "https://instagram.com/cafelix"


@pytest.mark.asyncio
async def test_sync_never_erases_a_hand_backfilled_link_when_the_pin_has_none(monkeypatch):
    changes = await _sync_and_get_update(monkeypatch, None)

    assert "instagram_url" not in changes
