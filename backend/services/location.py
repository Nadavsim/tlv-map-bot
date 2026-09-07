import re

import requests

# Covers the URL shapes Google Maps produces when someone taps "Share" on a
# pin or their own location: ?q=lat,lon, /@lat,lon,zoom (also inside
# /maps/place/.../@lat,lon,zoom), and the !3d..!4d.. pair embedded in some
# place-detail URLs. Order matters: a place-detail URL can contain BOTH an
# @lat,lon (the map viewport center, which can be panned away from the pin)
# and !3d..!4d.. (the actual precise place coordinate) - the more specific
# !3d!4d pattern must be tried first so it wins when both are present.
_COORD_PATTERNS = [
    re.compile(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)"),
    re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)"),
    re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)"),
]


def extract_coords_from_url(url: str) -> tuple[float, float] | None:
    for pattern in _COORD_PATTERNS:
        match = pattern.search(url)
        if match:
            return float(match.group(1)), float(match.group(2))
    return None


def resolve_maps_link(text: str) -> tuple[float, float] | None:
    """Pull lat/lon out of a pasted Google Maps link, following redirects for
    short links (maps.app.goo.gl) since the coordinates only appear in the
    fully-expanded URL, not the short one."""
    coords = extract_coords_from_url(text)
    if coords:
        return coords

    if "http://" not in text and "https://" not in text:
        return None

    try:
        resp = requests.get(text.strip(), timeout=5, allow_redirects=True)
        return extract_coords_from_url(resp.url)
    except requests.RequestException:
        return None


# Nominatim's usage policy requires a real identifying User-Agent (not the
# default requests one) and caps usage at ~1 req/sec - not a concern at this
# app's personal-project volume, so no explicit throttling needed here.
_NOMINATIM_HEADERS = {"User-Agent": "tlv-bot (personal project - github.com/Nadavsim/tlv-whatsapp-map-bot)"}


def geocode_address(text: str) -> tuple[float, float] | None:
    """Free-text address/landmark -> (lat, lon) via Nominatim (OpenStreetMap's
    free geocoder, no API key/billing). "Tel Aviv-Yafo" (the official
    municipality name) is appended to the query - plain "Tel Aviv" or no
    city at all is genuinely ambiguous in Israel (e.g. "Rothschild" is also
    a street name in Holon and Bat Yam), and this app's entire domain is
    Tel Aviv anyway, so it's a safe, deliberate bias rather than a
    restriction - the full text is still sent, so an address that already
    names a different city still resolves there."""
    params = {
        "q": f"{text.strip()}, Tel Aviv-Yafo",
        "format": "json",
        "limit": 1,
        "countrycodes": "il",
    }
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=_NOMINATIM_HEADERS,
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None
