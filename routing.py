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


def _fetch_eta_seconds(mode: str, origin: tuple[float, float], dest: tuple[float, float]) -> float | None:
    config = _MODE_CONFIG.get(mode)
    if not config:
        return None

    origin_lat, origin_lon = origin
    dest_lat, dest_lon = dest
    url = (
        f"{_OSRM_BASE}/{config['service']}/route/v1/{config['profile']}/"
        f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}?overview=false"
    )

    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data["routes"][0]["duration"]
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


async def get_eta_seconds(mode: str, origin: tuple[float, float], dest: tuple[float, float]) -> float | None:
    """Real road-network ETA in seconds, or None if routing failed/unavailable.

    Runs the blocking HTTP call in a thread so it doesn't stall the event loop.
    """
    return await asyncio.to_thread(_fetch_eta_seconds, mode, origin, dest)


def format_duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"{minutes} min"
    hours, rem_minutes = divmod(minutes, 60)
    return f"{hours}h {rem_minutes}min" if rem_minutes else f"{hours}h"
