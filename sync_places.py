import asyncio
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from db import ensure_indexes, get_places_collection
from parser import parse_kml_text

load_dotenv()

MYMAPS_ID = os.environ.get("MYMAPS_ID", "")
MYMAPS_KML_URL = os.environ.get(
    "MYMAPS_KML_URL",
    f"https://www.google.com/maps/d/kml?mid={MYMAPS_ID}&forcekml=1" if MYMAPS_ID else "",
)


def fetch_kml() -> str:
    if not MYMAPS_KML_URL:
        raise RuntimeError("Set MYMAPS_ID or MYMAPS_KML_URL in .env first")
    resp = requests.get(MYMAPS_KML_URL, timeout=30)
    resp.raise_for_status()
    return resp.text


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
    sync_time = datetime.now(timezone.utc)

    for place in places:
        await collection.update_one(
            {"name": place["name"]},
            {
                "$set": {
                    "category": place["category"],
                    "location": {
                        "type": "Point",
                        "coordinates": [place["longitude"], place["latitude"]],
                    },
                    "last_synced_at": sync_time,
                },
                # Only set on first insert - never overwrites an instagram_url
                # that was already backfilled/edited by hand (e.g. via Atlas UI
                # or seed_instagram_from_csv.py).
                "$setOnInsert": {"instagram_url": place["instagram_url"]},
            },
            upsert=True,
        )

    # Anything not touched this run was removed from the My Maps map.
    result = await collection.delete_many({"last_synced_at": {"$ne": sync_time}})
    if result.deleted_count:
        print(f"Removed {result.deleted_count} place(s) no longer on the map.")

    total = await collection.count_documents({})
    print(f"Sync complete. {total} places now in the database.")


if __name__ == "__main__":
    asyncio.run(sync())
