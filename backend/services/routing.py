import asyncio

import requests

from .resilience import FailureBackoff, TTLCache

# routing.openstreetmap.de (FOSSGIS) is a free public OSRM deployment with
# separate per-mode instances - unlike router.project-osrm.org's public demo,
# which only truly serves "driving" and silently reuses that graph for any
# other profile name in the URL.
_OSRM_BASE = "https://routing.openstreetmap.de"
_MODE_CONFIG = {
    "walking": {"service": "routed-foot", "profile": "foot"},
    "driving": {"service": "routed-car", "profile": "driving"},
}

# The public OSRM instance has no live traffic - a duration only changes when
# its underlying map data does - so an hour is conservative. Cached per
# (mode, origin, destination) pair rather than per batch, so a follow-up
# request that overlaps a previous one (same address, "show more") only pays
# for the destinations it hasn't seen. Only real durations are cached: None
# means "unreachable or the lookup failed" and is worth retrying.
_eta_cache = TTLCache(ttl_seconds=60 * 60, max_entries=5000)
_osrm_backoff = FailureBackoff(threshold=3, cooldown_seconds=30)


def _point_key(point: tuple[float, float]) -> tuple[float, float]:
    # ~1m of rounding, just to keep float noise from splitting one key in two.
    return round(point[0], 5), round(point[1], 5)


def _fetch_eta_seconds_batch(
    mode: str, origin: tuple[float, float], destinations: list[tuple[float, float]]
) -> list[float | None]:
    config = _MODE_CONFIG.get(mode)
    if not config:
        return [None] * len(destinations)

    if _osrm_backoff.is_open():
        # Cards fall back to distance-only when an ETA is None, so skipping
        # the call costs the user nothing they'd have had while OSRM is down.
        return [None] * len(destinations)

    origin_lat, origin_lon = origin
    coords = [f"{origin_lon},{origin_lat}"] + [f"{lon},{lat}" for lat, lon in destinations]
    # This OSRM deployment rejects the sources/destinations filter params
    # ("Query string malformed"), so request the full matrix instead and
    # slice out row 0 (origin -> each point), dropping index 0 (origin ->
    # itself) - still one HTTP request regardless of destination count.
    url = f"{_OSRM_BASE}/{config['service']}/table/v1/{config['profile']}/{';'.join(coords)}"

    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        durations = data["durations"][0][1:]
    except (requests.RequestException, KeyError, IndexError, ValueError):
        _osrm_backoff.record_failure()
        return [None] * len(destinations)

    _osrm_backoff.record_success()
    return durations


async def get_eta_seconds_batch(
    mode: str, origin: tuple[float, float], destinations: list[tuple[float, float]]
) -> list[float | None]:
    """Real road-network ETAs in seconds, one per destination, from a single
    OSRM /table/ request instead of one /route/ request per destination.
    Returns a list aligned with `destinations`; entries are None for any
    unreachable destination or if routing failed/is unavailable entirely.

    Runs the blocking HTTP call in a thread so it doesn't stall the event loop.
    Destinations already answered recently come from cache; only the rest go
    to OSRM.
    """
    if not destinations:
        return []

    origin_key = _point_key(origin)
    keys = [(mode, origin_key, _point_key(destination)) for destination in destinations]
    results = [_eta_cache.get(key) for key in keys]

    missing = [i for i, cached in enumerate(results) if cached is None]
    if missing:
        fetched = await asyncio.to_thread(
            _fetch_eta_seconds_batch, mode, origin, [destinations[i] for i in missing]
        )
        for i, seconds in zip(missing, fetched):
            results[i] = seconds
            if seconds is not None:
                _eta_cache.set(keys[i], seconds)
    return results


def format_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"{minutes} min"
    hours, rem_minutes = divmod(minutes, 60)
    return f"{hours}h {rem_minutes}min" if rem_minutes else f"{hours}h"
