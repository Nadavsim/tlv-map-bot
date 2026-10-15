"""Lists what visitors have reported about places ("closed" / "wrong
category"), most-reported first - the curator's view of backend.db's
`place_reports` collection.

    python -m scripts.show_reports                 # production (per .env)
    MONGODB_DB_NAME=tlvbot_staging python -m scripts.show_reports
    python -m scripts.show_reports --dismiss <place_id> [<place_id> ...]

Reports clear themselves when sync sees the map change (a removed place, or a
pin moved to another layer). `--dismiss` is for the other case: you checked
and the place is fine as it is, so the reports should stop showing."""

import argparse
import asyncio

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv

load_dotenv()

from backend import db  # noqa: E402

KIND_LABELS = {"closed": "closed", "wrong_category": "wrong category"}


def build_rows(reports: list[dict], places_by_id: dict) -> list[dict]:
    """Pure (no I/O): reports joined with the places as they are now, most
    reported first. A place's current name/category wins over the snapshot
    taken when it was reported."""
    rows = []
    for report in reports:
        place = places_by_id.get(report["place_id"])
        note = ""
        if place is None:
            note = "no longer on the map"
        elif report["kind"] == "wrong_category" and place.get("category") != report.get("category"):
            note = f"category is now {place.get('category')}"
        rows.append(
            {
                "place_id": str(report["place_id"]),
                "name": (place or {}).get("name") or report.get("name") or "?",
                "category": (place or {}).get("category") or report.get("category") or "?",
                "kind": report["kind"],
                "count": report.get("count", 0),
                "last_at": report.get("last_at"),
                "note": note,
            }
        )
    rows.sort(key=lambda r: (r["count"], r["last_at"].isoformat() if r["last_at"] else ""), reverse=True)
    return rows


def format_rows(rows: list[dict]) -> str:
    if not rows:
        return "No reports."
    lines = []
    for row in rows:
        last = row["last_at"].strftime("%Y-%m-%d") if row["last_at"] else "?"
        line = (
            f"{row['count']:>3}x  {KIND_LABELS.get(row['kind'], row['kind']):<14}  "
            f"{row['name']} ({row['category']})  last {last}  id={row['place_id']}"
        )
        if row["note"]:
            line += f"  [{row['note']}]"
        lines.append(line)
    return "\n".join(lines)


async def show() -> None:
    reports = [doc async for doc in db.get_place_reports_collection().find({})]
    place_ids = list({report["place_id"] for report in reports})
    places = db.get_places_collection().find({"_id": {"$in": place_ids}}, {"name": 1, "category": 1})
    places_by_id = {place["_id"]: place async for place in places}
    print(format_rows(build_rows(reports, places_by_id)))


async def dismiss(place_ids: list[str]) -> None:
    oids = []
    for raw in place_ids:
        try:
            oids.append(ObjectId(raw))
        except InvalidId:
            print(f"Skipping {raw!r}: not a place id.")
    removed = await db.clear_place_reports(oids)
    print(f"Dismissed {removed} report row(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dismiss", nargs="+", metavar="PLACE_ID", help="clear all reports for these places")
    args = parser.parse_args()
    asyncio.run(dismiss(args.dismiss) if args.dismiss else show())
