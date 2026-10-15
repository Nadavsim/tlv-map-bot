import os
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, OperationFailure

from .models import PlaceResult, SavedAddress, User
from .services import weather

# This app is about Tel Aviv specifically, regardless of where the server
# happens to run or what timezone a request's own clock is in - "closes at
# 23" always means 23:00 Israel time.
_TLV_TZ = ZoneInfo("Asia/Jerusalem")

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "tlvbot")

CATEGORIES_CACHE_TTL_SECONDS = 300

# Buckets for record_category_request() that aren't a real category name -
# kept as constants so app.py and db.py agree on the exact strings.
ANY_CATEGORY_KEY = "any_category"
UNMATCHED_KEY = "unmatched"
# Same collection, same idea, for the location box: how often a typed address
# found nothing / got a spelling suggestion. Counts only - the privacy policy
# says typed addresses are not stored, so no text is ever logged here.
LOCATION_UNRESOLVED_KEY = "location_unresolved"
LOCATION_CORRECTION_OFFERED_KEY = "location_correction_offered"

# How long a raw unmatched-query log entry sticks around before Mongo's TTL
# index auto-deletes it - long enough to review periodically for curation
# ideas, short enough not to grow the (free-tier, size-capped) database
# unbounded.
UNMATCHED_QUERIES_TTL_SECONDS = 90 * 24 * 60 * 60

# Mirrors models.Place - kept as a plain dict (rather than derived from the
# Pydantic model) because Mongo's $jsonSchema dialect (bsonType, etc.) isn't
# the same vocabulary as Pydantic's JSON Schema export, so auto-translating
# would be more fragile than just stating it twice.
PLACES_JSON_SCHEMA = {
    "bsonType": "object",
    "required": ["name", "category", "location"],
    "properties": {
        "name": {"bsonType": "string"},
        "category": {"bsonType": "string"},
        "location": {
            "bsonType": "object",
            "required": ["type", "coordinates"],
            "properties": {
                "type": {"enum": ["Point"]},
                "coordinates": {
                    "bsonType": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"bsonType": ["double", "int"]},
                },
            },
        },
        "instagram_url": {"bsonType": ["string", "null"]},
        "dietary_tags": {"bsonType": "array", "items": {"bsonType": "string"}},
        "price_tier": {"enum": ["$", "$$", "$$$", None]},
        "closes_at_hour": {"bsonType": ["int", "null"], "minimum": 0, "maximum": 23},
        "outdoor_seating": {"bsonType": "bool"},
        "last_synced_at": {"bsonType": ["date", "null"]},
    },
}

# Mirrors models.User, same reasoning as PLACES_JSON_SCHEMA above.
USERS_JSON_SCHEMA = {
    "bsonType": "object",
    "required": ["google_sub", "email", "name", "token_version", "created_at"],
    "properties": {
        "google_sub": {"bsonType": "string"},
        "email": {"bsonType": "string"},
        "name": {"bsonType": "string"},
        "picture_url": {"bsonType": ["string", "null"]},
        "token_version": {"bsonType": "int"},
        "saved_addresses": {
            "bsonType": "array",
            "items": {
                "bsonType": "object",
                "required": ["id", "label", "lat", "lon"],
                "properties": {
                    "id": {"bsonType": "string"},
                    "label": {"bsonType": "string"},
                    "lat": {"bsonType": "double"},
                    "lon": {"bsonType": "double"},
                },
            },
        },
        "created_at": {"bsonType": "date"},
    },
}

# A person's frequently-used manual addresses. A handful is the point (a
# place you actually go from), and the cap keeps what's stored about anyone
# small and bounded.
MAX_SAVED_ADDRESSES = 5
# 4 decimal places is ~11 m. "Which nearby place is closest" has no use for
# more, and not storing more precision than the feature needs is the cheapest
# privacy measure available - so it's applied at the storage layer itself.
SAVED_ADDRESS_COORD_DECIMALS = 4
SAVED_ADDRESS_LABEL_MAX_LENGTH = 80

# A person's favorite places. Bounded so what is stored about one account
# can't grow without limit on a free-tier database; generous enough that a
# real person won't hit it (the whole curated list is ~165 places).
MAX_FAVORITES = 100
# Central Tel Aviv - only used to run the favorites query when the caller has
# no location of its own and doesn't care about distance.
FAVORITES_REFERENCE_POINT = (32.0853, 34.7818)

# One document per (user, place) pair - a dedicated collection rather than an
# array on the user document, so "who favorited place X" stays a plain indexed
# query and a heavy user's favorites can't grow a single document unbounded.
# Both ids are stored as ObjectId (not the str form the JWT/API hands around)
# so a future $lookup from favorites into places joins on matching types.
# place_id points at places._id, which sync_places.py deliberately preserves
# across renames/small moves (proximity matching) - but a place removed from
# the map is deleted, leaving its favorites dangling; a listing query using
# $lookup + $unwind skips those naturally.
FAVORITES_JSON_SCHEMA = {
    "bsonType": "object",
    "required": ["user_id", "place_id", "created_at"],
    "properties": {
        "user_id": {"bsonType": "objectId"},
        "place_id": {"bsonType": "objectId"},
        "created_at": {"bsonType": "date"},
    },
}

_client: AsyncIOMotorClient | None = None
_categories_cache: list[str] | None = None
_categories_cache_expires_at: float = 0.0
_dietary_tags_cache: list[str] | None = None
_dietary_tags_cache_expires_at: float = 0.0


def _get_collection(name: str):
    """Lazily create the Mongo client so importing this module never requires
    MONGODB_URI to be set (needed for tests / tools that don't touch the DB)."""
    global _client
    if _client is None:
        if not MONGODB_URI:
            raise RuntimeError("MONGODB_URI is not set")
        _client = AsyncIOMotorClient(MONGODB_URI)
    return _client[MONGODB_DB_NAME][name]


async def ping_database() -> bool:
    """Cheap liveness check for /health - a real ping, not just "did the
    client construct", since a silent DB-connectivity failure is exactly the
    kind of outage this app has already had with nobody alerted."""
    try:
        client = get_places_collection().database.client
        await client.admin.command("ping")
        return True
    except Exception:
        return False


def get_places_collection():
    return _get_collection("places")


def get_category_stats_collection():
    return _get_collection("category_stats")


def get_unmatched_queries_collection():
    return _get_collection("unmatched_queries")


def get_users_collection():
    return _get_collection("users")


def get_favorites_collection():
    return _get_collection("favorites")


async def ensure_indexes() -> None:
    places = get_places_collection()
    await places.create_index([("location", "2dsphere")])

    # Older deployments have a unique index here (name used to be the
    # identity key). Mongo refuses to silently redefine an existing index's
    # options, so drop it first if it's still unique before recreating it as
    # a plain lookup index - identity is decided by location proximity now
    # (see find_nearby/sync_places.py), not name, since two real places can
    # share a name.
    existing_indexes = await places.index_information()
    name_index = existing_indexes.get("name_1")
    if name_index and name_index.get("unique"):
        await places.drop_index("name_1")

    await places.create_index("name")
    await places.create_index("category")

    await _ensure_schema_validator(places, "places", PLACES_JSON_SCHEMA)

    unmatched_queries = get_unmatched_queries_collection()
    await unmatched_queries.create_index("created_at", expireAfterSeconds=UNMATCHED_QUERIES_TTL_SECONDS)

    users = get_users_collection()
    await users.create_index("google_sub", unique=True)
    await _ensure_schema_validator(users, "users", USERS_JSON_SCHEMA)

    # user_id leads the compound key, so this one index also serves the
    # common "all favorites for this user" lookup - no separate user_id index.
    favorites = get_favorites_collection()
    await favorites.create_index([("user_id", 1), ("place_id", 1)], unique=True)
    await _ensure_schema_validator(favorites, "favorites", FAVORITES_JSON_SCHEMA)


async def _ensure_schema_validator(collection, name: str, schema: dict) -> None:
    """Defense-in-depth: enforce a collection's $jsonSchema at the database
    layer itself, so a malformed document gets caught regardless of what
    wrote it (a bad script, a manual Compass edit) - not just whatever
    happens to run it through the matching Pydantic model first.

    validationAction "warn" only logs a violation to the Atlas server log
    instead of rejecting the write. "error" would be stricter, but risks
    locking out a legitimate write if a schema ever drifts even slightly
    from what the app actually writes - start permissive and only tighten to
    "error" once it's been observed running clean for a while."""
    database = collection.database
    validator = {"$jsonSchema": schema}
    try:
        await database.command(
            {
                "collMod": name,
                "validator": validator,
                "validationLevel": "moderate",
                "validationAction": "warn",
            }
        )
    except OperationFailure:
        # collMod fails if the collection doesn't exist yet (fresh database).
        await database.create_collection(
            name,
            validator=validator,
            validationLevel="moderate",
            validationAction="warn",
        )


def invalidate_categories_cache() -> None:
    global _categories_cache, _categories_cache_expires_at
    _categories_cache = None
    _categories_cache_expires_at = 0.0


async def get_categories() -> list[str]:
    """Cached for CATEGORIES_CACHE_TTL_SECONDS - this list only actually
    changes when sync_places.py runs, so querying Mongo on every chat message
    is unnecessary. Call invalidate_categories_cache() to force a refresh."""
    global _categories_cache, _categories_cache_expires_at
    now = time.monotonic()
    if _categories_cache is not None and now < _categories_cache_expires_at:
        return _categories_cache

    places = get_places_collection()
    _categories_cache = sorted(await places.distinct("category"))
    _categories_cache_expires_at = now + CATEGORIES_CACHE_TTL_SECONDS
    return _categories_cache


def invalidate_dietary_tags_cache() -> None:
    global _dietary_tags_cache, _dietary_tags_cache_expires_at
    _dietary_tags_cache = None
    _dietary_tags_cache_expires_at = 0.0


async def get_dietary_tags() -> list[str]:
    """Same caching approach as get_categories() - the live set of dietary
    tags actually in use (from My Maps pin descriptions), so the LLM can
    match free text against real, current tags rather than a hardcoded and
    inevitably stale list."""
    global _dietary_tags_cache, _dietary_tags_cache_expires_at
    now = time.monotonic()
    if _dietary_tags_cache is not None and now < _dietary_tags_cache_expires_at:
        return _dietary_tags_cache

    places = get_places_collection()
    # distinct() on an array field automatically flattens to the unique
    # scalar values across every document's array - no special handling
    # needed for the "field is a list" part.
    _dietary_tags_cache = sorted(await places.distinct("dietary_tags"))
    _dietary_tags_cache_expires_at = now + CATEGORIES_CACHE_TTL_SECONDS
    return _dietary_tags_cache


async def record_category_request(key: str) -> None:
    """Bumps a demand counter for a category (or ANY_CATEGORY_KEY /
    UNMATCHED_KEY) - a lightweight, curation-facing signal for which
    categories are actually wanted, read directly in Atlas rather than
    through any app UI (see log_unmatched_query for the companion "what
    exactly did they ask for" detail)."""
    stats = get_category_stats_collection()
    await stats.update_one({"_id": key}, {"$inc": {"count": 1}}, upsert=True)


async def log_unmatched_query(text: str) -> None:
    """Logs the raw text of a query the LLM couldn't match to any known
    category, so it can be read later (directly in Atlas) for ideas on
    which categories to add. Auto-expires via the TTL index set up in
    ensure_indexes() - see UNMATCHED_QUERIES_TTL_SECONDS."""
    queries = get_unmatched_queries_collection()
    await queries.insert_one({"text": text, "created_at": datetime.now(timezone.utc)})


def build_geo_pipeline(
    category: str | None,
    lat: float,
    lon: float,
    limit: int = 3,
    offset: int = 0,
    tag: str | None = None,
    price: str | None = None,
    place_ids: list | None = None,
) -> list[dict]:
    """Pure function (no I/O) so the query shape can be unit tested without a
    real MongoDB connection. category=None means "any category" (surprise me).
    offset supports "show more" - skipping past results already shown for the
    same query rather than re-fetching and re-displaying the top matches.
    tag filters to places whose dietary_tags array contains that value -
    Mongo matches an array field against a scalar query value by "contains"
    automatically, no special operator needed. price filters to places whose
    price_tier is exactly that tier (a place has one, unlike tags).
    place_ids restricts the search to those documents (a person's favorites,
    ordered nearest-first like any other result)."""
    query: dict = {}
    if category:
        query["category"] = category
    if tag:
        query["dietary_tags"] = tag
    if price:
        query["price_tier"] = price
    if place_ids is not None:
        query["_id"] = {"$in": place_ids}
    pipeline = [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "distance",
                "spherical": True,
                "query": query,
            }
        },
    ]
    if offset:
        pipeline.append({"$skip": offset})
    pipeline.append({"$limit": limit})
    return pipeline


def _is_likely_closed(place: PlaceResult, current_hour: int) -> bool:
    if place.closes_at_hour is None:
        return False
    if place.closes_at_hour == 0:
        # "#until00" means "open past midnight" - never a closed signal.
        return False
    return current_hour >= place.closes_at_hour


def _is_likely_unpleasant(place: PlaceResult, is_raining: bool) -> bool:
    return is_raining and place.outdoor_seating


def deprioritize_unlikely_matches(
    places: list[PlaceResult], current_hour: int, is_raining: bool
) -> list[PlaceResult]:
    """Pure, no I/O - reorders (never excludes) already-fetched candidates so
    a place that's likely closed right now, or has outdoor-only seating
    during rain, sorts after everything else. Distance order is preserved
    within each bucket, so a query where neither signal applies to any
    result comes back in exactly the same order $geoNear returned it in."""

    def flagged(place: PlaceResult) -> bool:
        return _is_likely_closed(place, current_hour) or _is_likely_unpleasant(place, is_raining)

    fine = [p for p in places if not flagged(p)]
    later = [p for p in places if flagged(p)]
    return fine + later


def _place_result(doc: dict) -> PlaceResult:
    """A $geoNear document as a PlaceResult, with Mongo's _id as `id`."""
    raw_id = doc.get("_id")
    return PlaceResult(**{**doc, "id": str(raw_id) if raw_id is not None else None})


async def find_nearest(
    category: str | None,
    lat: float,
    lon: float,
    limit: int = 3,
    offset: int = 0,
    tag: str | None = None,
    price: str | None = None,
) -> list[PlaceResult]:
    places = get_places_collection()
    pipeline = build_geo_pipeline(category, lat, lon, limit, offset, tag, price)
    matches = [_place_result(doc) async for doc in places.aggregate(pipeline)]
    current_hour = datetime.now(_TLV_TZ).hour
    is_raining = await weather.is_raining_now(lat, lon)
    return deprioritize_unlikely_matches(matches, current_hour, is_raining)


def build_proximity_pipeline(
    lat: float, lon: float, max_meters: float, query: dict | None = None
) -> list[dict]:
    """Pure function (no I/O), mirrors build_geo_pipeline's testability."""
    return [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "distance",
                "maxDistance": max_meters,
                "spherical": True,
                "query": query or {},
            }
        },
        {"$limit": 1},
    ]


async def find_nearby(
    lat: float, lon: float, max_meters: float = 30, query: dict | None = None
) -> dict | None:
    """The nearest existing place within max_meters, or None. Used by
    sync_places.py to decide "is this the same physical place" independent of
    its name - so a rename doesn't look like a delete+insert.

    Pass `query` to exclude documents already matched earlier in the same
    sync run (see sync_places.py) - otherwise two genuinely distinct places
    that happen to sit within max_meters of each other would collide into
    one document."""
    places = get_places_collection()
    pipeline = build_proximity_pipeline(lat, lon, max_meters, query)
    async for doc in places.aggregate(pipeline):
        return doc
    return None


async def get_user_by_google_sub(google_sub: str) -> tuple[str, User] | None:
    """Returns (id, User) or None. The id is returned separately (not on
    User itself) for the same reason PlaceResult doesn't carry Mongo's _id -
    it's a Mongo-layer detail, not part of the domain model."""
    users = get_users_collection()
    doc = await users.find_one({"google_sub": google_sub})
    if doc is None:
        return None
    return str(doc["_id"]), User(**doc)


async def get_user_by_id(user_id: str) -> User | None:
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        return None
    users = get_users_collection()
    doc = await users.find_one({"_id": object_id})
    return User(**doc) if doc else None


async def create_user(google_sub: str, email: str, name: str, picture_url: str | None) -> tuple[str, User]:
    """Called only on a first sign-in for this google_sub - an existing user
    is looked up via get_user_by_google_sub instead, never re-inserted."""
    user = User(
        google_sub=google_sub,
        email=email,
        name=name,
        picture_url=picture_url,
        created_at=datetime.now(timezone.utc),
    )
    users = get_users_collection()
    result = await users.insert_one(user.model_dump())
    return str(result.inserted_id), user


def round_saved_coord(value: float) -> float:
    return round(value, SAVED_ADDRESS_COORD_DECIMALS)


def normalize_address_label(label: str, lat: float, lon: float) -> str:
    """What gets stored as the display text of a saved address. The typed
    text is kept when it reads as an address; a pasted link or anything
    empty is replaced with the (rounded) coordinates instead, so the
    collection never ends up holding arbitrary URLs - which can carry
    tracking parameters or a place name - just because someone pasted one
    into the location box."""
    text = " ".join(label.split())
    lowered = text.lower()
    if not text or "://" in text or lowered.startswith(("www.", "maps.", "goo.gl", "g.co")):
        return f"{lat:.{SAVED_ADDRESS_COORD_DECIMALS}f}, {lon:.{SAVED_ADDRESS_COORD_DECIMALS}f}"
    return text[:SAVED_ADDRESS_LABEL_MAX_LENGTH]


async def list_saved_addresses(user_id: str) -> list[SavedAddress] | None:
    """None means the user doesn't exist (e.g. deleted since the token was
    issued) - distinct from a real user with nothing saved yet."""
    user = await get_user_by_id(user_id)
    return None if user is None else user.saved_addresses


async def add_saved_address(
    user_id: str, label: str, lat: float, lon: float
) -> tuple[str, SavedAddress | None]:
    """Returns (status, address): "added", "exists" (the same spot is
    already saved - returned as-is rather than duplicated), "full" (at
    MAX_SAVED_ADDRESSES), or "no_user"."""
    lat, lon = round_saved_coord(lat), round_saved_coord(lon)
    user = await get_user_by_id(user_id)
    if user is None:
        return "no_user", None
    for existing in user.saved_addresses:
        if existing.lat == lat and existing.lon == lon:
            return "exists", existing
    if len(user.saved_addresses) >= MAX_SAVED_ADDRESSES:
        return "full", None

    address = SavedAddress(id=uuid.uuid4().hex, label=normalize_address_label(label, lat, lon), lat=lat, lon=lon)
    users = get_users_collection()
    # The read above is only for choosing a status; the cap is enforced again
    # in the update's own filter so two concurrent adds can't both slip in
    # past the limit (the Nth element existing means the array is full).
    result = await users.update_one(
        {"_id": ObjectId(user_id), f"saved_addresses.{MAX_SAVED_ADDRESSES - 1}": {"$exists": False}},
        {"$push": {"saved_addresses": address.model_dump()}},
    )
    if result.matched_count == 0:
        return "full", None
    return "added", address


async def remove_saved_address(user_id: str, address_id: str) -> bool:
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        return False
    users = get_users_collection()
    result = await users.update_one({"_id": object_id}, {"$pull": {"saved_addresses": {"id": address_id}}})
    return result.modified_count > 0


async def find_favorite_places(
    user_id: str, lat: float | None = None, lon: float | None = None
) -> list[PlaceResult] | None:
    """The user's favorites as ordinary results, nearest to (lat, lon) first -
    the same $geoNear shape every other result uses, so distance, ETA, map and
    share all work on them unchanged. A favorite whose place has since been
    removed from the map simply isn't in `places` any more and drops out here
    (it is a dangling reference, never an error)."""
    if await get_user_by_id(user_id) is None:
        return None
    cursor = get_favorites_collection().find({"user_id": ObjectId(user_id)}, {"place_id": 1})
    place_ids = [doc["place_id"] async for doc in cursor]
    if not place_ids:
        return []
    if lat is None or lon is None:
        # No position (the menu's list): any fixed point will do, since the
        # caller ignores the distances - $geoNear just needs one.
        lat, lon = FAVORITES_REFERENCE_POINT
    pipeline = build_geo_pipeline(None, lat, lon, limit=MAX_FAVORITES, place_ids=place_ids)
    return [_place_result(doc) async for doc in get_places_collection().aggregate(pipeline)]


async def add_favorite(user_id: str, place_id: str) -> str:
    """"added", "exists" (idempotent - already favorited), "full" (at
    MAX_FAVORITES), "no_place" (no such place, or a malformed id) or
    "no_user"."""
    try:
        user_oid, place_oid = ObjectId(user_id), ObjectId(place_id)
    except InvalidId:
        return "no_place"
    if await get_user_by_id(user_id) is None:
        return "no_user"
    if await get_places_collection().find_one({"_id": place_oid}, {"_id": 1}) is None:
        return "no_place"
    favorites = get_favorites_collection()
    if await favorites.find_one({"user_id": user_oid, "place_id": place_oid}, {"_id": 1}) is not None:
        return "exists"
    if await favorites.count_documents({"user_id": user_oid}) >= MAX_FAVORITES:
        return "full"
    try:
        await favorites.insert_one(
            {"user_id": user_oid, "place_id": place_oid, "created_at": datetime.now(timezone.utc)}
        )
    except DuplicateKeyError:
        # A concurrent tap won the race - the unique index is the real guard.
        return "exists"
    return "added"


async def remove_favorite(user_id: str, place_id: str) -> bool:
    try:
        user_oid, place_oid = ObjectId(user_id), ObjectId(place_id)
    except InvalidId:
        return False
    result = await get_favorites_collection().delete_one({"user_id": user_oid, "place_id": place_oid})
    return result.deleted_count > 0


async def delete_user(user_id: str) -> bool:
    """Removes the account and everything tied to it: saved addresses are
    embedded in the user document and go with it; favorites live in their own
    collection, so they're cascaded explicitly. Any future collection keyed by
    user has to be added here too."""
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        return False
    # Favorites first: if the user delete then failed, the account is still
    # intact and the call can simply be retried, rather than leaving orphaned
    # favorites for an account that no longer exists.
    await get_favorites_collection().delete_many({"user_id": object_id})
    result = await get_users_collection().delete_one({"_id": object_id})
    return result.deleted_count > 0


async def revoke_user_sessions(user_id: str) -> None:
    """Bumps token_version, invalidating every refresh token issued before
    this call (see User.token_version) - what "sign out" actually revokes
    server-side, not just what the client discards."""
    users = get_users_collection()
    await users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"token_version": 1}})
