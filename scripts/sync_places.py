import asyncio
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from backend.db import (
    ensure_indexes,
    find_nearby,
    get_places_collection,
    invalidate_categories_cache,
    invalidate_dietary_tags_cache,
)
from backend.models import GeoPoint, Place
from backend.parser import parse_kml_text

load_dotenv()

MYMAPS_ID = os.environ.get("MYMAPS_ID", "")
MYMAPS_KML_URL = os.environ.get(
    "MYMAPS_KML_URL",
    f"https://www.google.com/maps/d/kml?mid={MYMAPS_ID}&forcekml=1" if MYMAPS_ID else "",
)

# If a sync would remove more than this fraction of existing places, treat it
# as a likely partial/truncated fetch and abort rather than silently deleting
# real data. Set FORCE_SYNC=1 to bypass (e.g. you really did prune the map).
TRUNCATION_GUARD_RATIO = 0.7

PROXIMITY_MATCH_METERS = 30


def fetch_kml() -> str:
    if not MYMAPS_KML_URL:
        raise RuntimeError("Set MYMAPS_ID or MYMAPS_KML_URL in .env first")
    resp = requests.get(MYMAPS_KML_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


def looks_like_truncated_fetch(
    new_count: int, existing_count: int, ratio: float = TRUNCATION_GUARD_RATIO
) -> bool:
    """Pure function (no I/O) so this safety check is unit testable."""
    return existing_count > 0 and new_count < existing_count * ratio


async def sync() -> None:
    print("Fetching latest map from Google My Maps...")
    kml_text = fetch_kml()

    places = parse_kml_text(kml_text)
    print(f"Parsed {len(places)} places from the map.")

    if not places:
        raise RuntimeError(
            "Parsed 0 places from the map - aborting without touching the database. "
            "Check that the map is shared publicly and MYMAPS_ID/MYMAPS_KML_URL is correct."
        )

    await ensure_indexes()
    collection = get_places_collection()

    existing_count = await collection.count_documents({})
    if looks_like_truncated_fetch(len(places), existing_count) and not os.environ.get("FORCE_SYNC"):
        raise RuntimeError(
            f"Parsed only {len(places)} places, but the database currently has {existing_count} - "
            "this looks like a partial/truncated fetch (rate limiting, a My Maps export glitch, "
            "or a temporarily unshared layer), so nothing was deleted. If you really did remove "
            "that many places from the map on purpose, rerun with FORCE_SYNC=1."
        )

    sync_time = datetime.now(timezone.utc)
    not_yet_touched_this_run = {"last_synced_at": {"$ne": sync_time}}

    for place in places:
        # Validated against models.Place before it ever reaches Mongo - catches
        # a malformed parsed place (wrong type, missing field) here, with a
        # clear error, rather than writing bad data silently.
        validated = Place(
            name=place["name"],
            category=place["category"],
            location=GeoPoint(coordinates=(place["longitude"], place["latitude"])),
            instagram_url=place["instagram_url"],
            dietary_tags=place["dietary_tags"],
            price_tier=place["price_tier"],
            last_synced_at=sync_time,
        )
        location_doc = validated.location.model_dump()

        # Matched by physical proximity, not name - a renamed pin is still
        # "the same place" and keeps its _id (and any manually-backfilled
        # instagram_url), instead of looking like a delete+insert. Excluding
        # documents already touched this run stops two genuinely distinct,
        # closely-spaced places (e.g. two kiosks in the same food court)
        # from colliding into one.
        existing = await find_nearby(
            place["latitude"], place["longitude"], PROXIMITY_MATCH_METERS, query=not_yet_touched_this_run
        )
        if existing:
            await collection.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "name": validated.name,
                        "category": validated.category,
                        "location": location_doc,
                        "dietary_tags": validated.dietary_tags,
                        "price_tier": validated.price_tier,
                        "last_synced_at": validated.last_synced_at,
                    }
                },
            )
        else:
            await collection.insert_one(
                {
                    "name": validated.name,
                    "category": validated.category,
                    "location": location_doc,
                    "instagram_url": validated.instagram_url,
                    "dietary_tags": validated.dietary_tags,
                    "price_tier": validated.price_tier,
                    "last_synced_at": validated.last_synced_at,
                }
            )

    # Anything not touched this run is no longer on the map at that location.
    result = await collection.delete_many(not_yet_touched_this_run)
    if result.deleted_count:
        print(f"Removed {result.deleted_count} place(s) no longer on the map.")

    invalidate_categories_cache()

    total = await collection.count_documents({})
    print(f"Sync complete. {total} places now in the database.")


if __name__ == "__main__":
    asyncio.run(sync())
