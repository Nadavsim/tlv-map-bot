"""Pydantic schema for the `places` MongoDB collection - the single source of
truth for what a place document looks like. Used to validate data before it's
written (scripts/sync_places.py) and to give typed access to data read back
out (db.py, app.py) instead of passing raw dicts around."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class GeoPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # GeoJSON order: [longitude, latitude]

    @property
    def longitude(self) -> float:
        return self.coordinates[0]

    @property
    def latitude(self) -> float:
        return self.coordinates[1]


class Place(BaseModel):
    """A place document as stored in MongoDB (no _id or computed fields)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    category: str
    location: GeoPoint
    instagram_url: str | None = None
    # Free-form (whatever hashtag is typed into the pin's My Maps
    # description, e.g. "#kosher #vegan") rather than a fixed/validated
    # set - mirrors category itself being whatever a My Maps layer is
    # named, not a hardcoded list.
    dietary_tags: list[str] = []
    # "$"/"$$"/"$$$", typed into the pin description as "#$$" (see
    # parser._PRICE_RE) - a place has exactly one, unlike dietary_tags.
    price_tier: Literal["$", "$$", "$$$"] | None = None
    last_synced_at: datetime | None = None


class PlaceResult(Place):
    """A Place as returned by a $geoNear query - adds the distance in meters
    that MongoDB computes and attaches to each result."""

    distance: float
