import os
import time

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "tlvbot")

CATEGORIES_CACHE_TTL_SECONDS = 300

_client: AsyncIOMotorClient | None = None
_categories_cache: list[str] | None = None
_categories_cache_expires_at: float = 0.0


def get_places_collection():
    """Lazily create the Mongo client so importing this module never requires
    MONGODB_URI to be set (needed for tests / tools that don't touch the DB)."""
    global _client
    if _client is None:
        if not MONGODB_URI:
            raise RuntimeError("MONGODB_URI is not set")
        _client = AsyncIOMotorClient(MONGODB_URI)
    return _client[MONGODB_DB_NAME]["places"]


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


def build_geo_pipeline(category: str | None, lat: float, lon: float, limit: int = 3) -> list[dict]:
    """Pure function (no I/O) so the query shape can be unit tested without a
    real MongoDB connection. category=None means "any category" (surprise me)."""
    return [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "distance",
                "spherical": True,
                "query": {"category": category} if category else {},
            }
        },
        {"$limit": limit},
    ]


async def find_nearest(category: str | None, lat: float, lon: float, limit: int = 3) -> list[dict]:
    places = get_places_collection()
    pipeline = build_geo_pipeline(category, lat, lon, limit)
    return [doc async for doc in places.aggregate(pipeline)]


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
