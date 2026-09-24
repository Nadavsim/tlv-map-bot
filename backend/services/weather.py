import asyncio
import time

import requests

# Open-Meteo - free, keyless, no billing (same reasoning as OSRM/Nominatim
# elsewhere in this app). "current.precipitation" is the last hour's
# precipitation in mm; >0 is treated as "raining" for the purposes of
# deprioritizing outdoor-only seating.
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Weather doesn't change fast enough to need a fresh lookup on every single
# chat request - a single citywide cache (Tel Aviv is small enough that
# this is a reasonable proxy regardless of exactly where within it a user
# is) keyed by nothing but time, same TTL-cache shape as db.py's
# categories/dietary-tags caches.
_CACHE_TTL_SECONDS = 600
_cache_expires_at = 0.0
_cache_value = False


def _fetch_is_raining(lat: float, lon: float) -> bool:
    try:
        resp = requests.get(
            _FORECAST_URL,
            params={"latitude": lat, "longitude": lon, "current": "precipitation"},
            timeout=5,
        )
        resp.raise_for_status()
        return float(resp.json()["current"]["precipitation"]) > 0
    except (requests.RequestException, KeyError, TypeError, ValueError):
        # A failed lookup should never block a chat reply or skew results -
        # "unknown" defaults to "not raining" so outdoor places aren't
        # deprioritized just because this one free service hiccuped.
        return False


async def is_raining_now(lat: float, lon: float) -> bool:
    """Used to quietly deprioritize outdoor-seating-only places when it's
    actually raining right now (see db.deprioritize_unlikely_matches)."""
    global _cache_expires_at, _cache_value
    now = time.monotonic()
    if now < _cache_expires_at:
        return _cache_value

    _cache_value = await asyncio.to_thread(_fetch_is_raining, lat, lon)
    _cache_expires_at = now + _CACHE_TTL_SECONDS
    return _cache_value
