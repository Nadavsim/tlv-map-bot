"""One-time migration: backfill instagram_url for places already in MongoDB
from the legacy cleaned_places.csv (which had Instagram links added by hand -
the raw KML export doesn't carry them). Run this once, after the first
sync_places.py run, if you're migrating from the old Postgres-based bot.

Matches by exact place name, same as sync_places.py's upsert key.
"""

import asyncio
import sys

import pandas as pd

from backend.db import get_places_collection


async def seed(csv_path: str = "data/cleaned_places.csv") -> None:
    df = pd.read_csv(csv_path)
    collection = get_places_collection()

    updated = 0
    skipped = 0
    for _, row in df.iterrows():
        ig_url = row.get("Instagram")
        if pd.isna(ig_url) or not str(ig_url).strip():
            continue

        result = await collection.update_one(
            {"name": str(row["Name"]).strip()},
            {"$set": {"instagram_url": str(ig_url).strip()}},
        )
        if result.matched_count:
            updated += 1
        else:
            skipped += 1

    print(f"Updated {updated} place(s) with an Instagram link.")
    if skipped:
        print(f"{skipped} name(s) from the CSV had no matching place in the database (renamed/removed on the map?).")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/cleaned_places.csv"
    asyncio.run(seed(path))
