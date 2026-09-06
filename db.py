import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGODB_URI = os.environ.get("MONGODB_URI", "")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "tlvbot")

_client: AsyncIOMotorClient | None = None


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
    await places.create_index("name", unique=True)
    await places.create_index("category")


async def get_categories() -> list[str]:
    places = get_places_collection()
    return sorted(await places.distinct("category"))


def build_geo_pipeline(category: str, lat: float, lon: float, limit: int = 3) -> list[dict]:
    """Pure function (no I/O) so the query shape can be unit tested without a
    real MongoDB connection."""
    return [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "distance",
                "spherical": True,
                "query": {"category": category},
            }
        },
        {"$limit": limit},
    ]


async def find_nearest(category: str, lat: float, lon: float, limit: int = 3) -> list[dict]:
    places = get_places_collection()
    pipeline = build_geo_pipeline(category, lat, lon, limit)
    return [doc async for doc in places.aggregate(pipeline)]
