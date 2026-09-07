import asyncio

import requests

# routing.openstreetmap.de (FOSSGIS) is a free public OSRM deployment with
# separate per-mode instances - unlike router.project-osrm.org's public demo,
# which only truly serves "driving" and silently reuses that graph for any
# other profile name in the URL.
_OSRM_BASE = "https://routing.openstreetmap.de"
_MODE_CONFIG = {
    "walking": {"service": "routed-foot", "profile": "foot"},
    "driving": {"service": "routed-car", "profile": "driving"},
}


def _fetch_eta_seconds_batch(
    mode: str, origin: tuple[float, float], destinations: list[tuple[float, float]]
) -> list[float | None]:
    config = _MODE_CONFIG.get(mode)
    if not config:
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
        return data["durations"][0][1:]
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return [None] * len(destinations)


async def get_eta_seconds_batch(
    mode: str, origin: tuple[float, float], destinations: list[tuple[float, float]]
) -> list[float | None]:
    """Real road-network ETAs in seconds, one per destination, from a single
    OSRM /table/ request instead of one /route/ request per destination.
    Returns a list aligned with `destinations`; entries are None for any
    unreachable destination or if routing failed/is unavailable entirely.

    Runs the blocking HTTP call in a thread so it doesn't stall the event loop.
    """
    if not destinations:
        return []
    return await asyncio.to_thread(_fetch_eta_seconds_batch, mode, origin, destinations)


def format_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"{minutes} min"
    hours, rem_minutes = divmod(minutes, 60)
    return f"{hours}h {rem_minutes}min" if rem_minutes else f"{hours}h"
