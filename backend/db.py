import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from .models import PlaceResult, User
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
    category: str | None, lat: float, lon: float, limit: int = 3, offset: int = 0, tag: str | None = None
) -> list[dict]:
    """Pure function (no I/O) so the query shape can be unit tested without a
    real MongoDB connection. category=None means "any category" (surprise me).
    offset supports "show more" - skipping past results already shown for the
    same query rather than re-fetching and re-displaying the top matches.
    tag filters to places whose dietary_tags array contains that value -
    Mongo matches an array field against a scalar query value by "contains"
    automatically, no special operator needed."""
    query: dict = {}
    if category:
        query["category"] = category
    if tag:
        query["dietary_tags"] = tag
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


async def find_nearest(
    category: str | None,
    lat: float,
    lon: float,
    limit: int = 3,
    offset: int = 0,
    tag: str | None = None,
) -> list[PlaceResult]:
    places = get_places_collection()
    pipeline = build_geo_pipeline(category, lat, lon, limit, offset, tag)
    matches = [PlaceResult(**doc) async for doc in places.aggregate(pipeline)]
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


async def revoke_user_sessions(user_id: str) -> None:
    """Bumps token_version, invalidating every refresh token issued before
    this call (see User.token_version) - what "sign out" actually revokes
    server-side, not just what the client discards."""
    users = get_users_collection()
    await users.update_one({"_id": ObjectId(user_id)}, {"$inc": {"token_version": 1}})
