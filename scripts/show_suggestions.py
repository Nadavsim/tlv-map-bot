"""Lists the places visitors have suggested - the curator's view of backend.db's
`place_suggestions` collection. Nothing here is ever shown to other visitors.

    python -m scripts.show_suggestions                     # new ones, production (per .env)
    MONGODB_DB_NAME=tlvbot_staging python -m scripts.show_suggestions
    python -m scripts.show_suggestions --all               # every status
    python -m scripts.show_suggestions --contact           # also show the suggester's email
    python -m scripts.show_suggestions --count             # just the number waiting
    python -m scripts.show_suggestions --mark added <id> [<id> ...]
                                                           # added | declined | duplicate

A suggestion carries the category the person picked, which is the My Maps layer
to put the pin in. "Already on the map" flags a suggestion whose coordinates
fall within a few dozen metres of a place you already have. Suggestions are
deleted automatically 180 days after they were made, whatever their status."""

import argparse
import asyncio

from dotenv import load_dotenv

load_dotenv()

from backend import db  # noqa: E402

DUPLICATE_RADIUS_METERS = 60


def safe(value: object, max_len: int = 300) -> str:
    """Printable plain text for a terminal. Stored text is sanitised on the way
    in; this cleans it again so a stored escape sequence can never act on the
    curator's terminal even if that ever changes."""
    if not isinstance(value, str):
        return "?" if value is None else str(value)[:max_len]
    return " ".join("".join(ch if ch.isprintable() else " " for ch in value).split())[:max_len]


def build_rows(suggestions: list[dict], nearby_by_id: dict, include_email: bool = False) -> list[dict]:
    """Pure (no I/O): what to print for each suggestion. `nearby_by_id` maps a
    suggestion's _id to the existing place within the duplicate radius, if any."""
    rows = []
    for item in suggestions:
        nearby = nearby_by_id.get(item["_id"])
        row = {
            "id": str(item["_id"]),
            "what": safe(item.get("place_text")) if item.get("place_text") else "(no name found - open the link)",
            "category": safe(item.get("category")),
            "link": safe(item.get("link")) if item.get("link") else "",
            "who": safe(item.get("name")) if item.get("name") else "(account deleted)",
            "when": item["created_at"].strftime("%Y-%m-%d") if item.get("created_at") else "?",
            "status": safe(item.get("status")),
            "already": f"{safe(nearby.get('name'))} ({safe(nearby.get('category'))})" if nearby else "",
        }
        if include_email:
            row["email"] = safe(item.get("email")) if item.get("email") else ""
        rows.append(row)
    return rows


def format_row(row: dict) -> str:
    lines = [f"  {row['what']}   [{row['category']}]   from {row['who']}, {row['when']}   id={row['id']}"]
    if row["link"]:
        lines.append(f"      link: {row['link']}")
    if row.get("email"):
        lines.append(f"      contact: {row['email']}")
    if row["already"]:
        lines.append(f"      ALREADY ON THE MAP as {row['already']}")
    if row["status"] != "new":
        lines.append(f"      status: {row['status']}")
    return "\n".join(lines)


async def _nearby(suggestions: list[dict]) -> dict:
    found = {}
    for item in suggestions:
        if item.get("lat") is not None and item.get("lon") is not None:
            place = await db.nearest_place_within(item["lat"], item["lon"], DUPLICATE_RADIUS_METERS)
            if place:
                found[item["_id"]] = place
    return found


async def _list(show_all: bool, include_email: bool, count_only: bool) -> None:
    items = await db.list_suggestions(None if show_all else "new", include_email=include_email)
    if count_only:
        print(len(items))
        return
    if not items:
        print("No suggestions waiting." if not show_all else "No suggestions.")
        return
    rows = build_rows(items, await _nearby(items), include_email)
    print(f"{len(rows)} suggestion{'s' if len(rows) != 1 else ''}{'' if show_all else ' waiting'}:\n")
    print("\n\n".join(format_row(row) for row in rows))
    print("\nClose one with:  python -m scripts.show_suggestions --mark added|declined|duplicate <id>")


async def _mark(status: str, ids: list[str]) -> None:
    for suggestion_id in ids:
        ok = await db.mark_suggestion(suggestion_id, status)
        print(f"{'marked ' + status if ok else 'not found / invalid'}: {suggestion_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show or close place suggestions.")
    parser.add_argument("--all", action="store_true", help="every status, not just new")
    parser.add_argument("--contact", action="store_true", help="also show the suggester's email")
    parser.add_argument("--count", action="store_true", help="print only how many are waiting")
    parser.add_argument("--mark", choices=[s for s in db.SUGGESTION_STATUSES if s != "new"])
    parser.add_argument("ids", nargs="*", help="suggestion ids for --mark")
    args = parser.parse_args()
    if args.mark:
        if not args.ids:
            parser.error("--mark needs at least one id")
        asyncio.run(_mark(args.mark, args.ids))
    else:
        asyncio.run(_list(args.all, args.contact, args.count))


if __name__ == "__main__":
    main()
