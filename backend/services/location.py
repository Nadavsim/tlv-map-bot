import re
from urllib.parse import parse_qs, unquote_plus, urlparse

import requests

from .resilience import FailureBackoff, TTLCache

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


# Not every Google Maps link carries coordinates: a place shared by name (very
# common for a business, whose link then holds only its name + address and an
# opaque feature id) expands to /maps/place/<name>/data=!1s0x...:0x... with no
# lat/lon anywhere, and so do ?q=<text> and search links. Those are resolved
# through the place text instead - see geocode_candidates.
_PLACE_PATH_RE = re.compile(r"/maps/(?:place|search)/([^/@?]+)")
# Google appends invisible bidi-control characters to RTL place names.
_BIDI_CONTROLS_RE = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_POSTCODE_TAIL_RE = re.compile(r"[,\s]+\d{5,7}$")
_COORD_PAIR_RE = re.compile(r"-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?")
# google.com, google.co.il, google.com.au, google.de ... and goo.gl - and
# nothing that merely starts with one of them (google.com.evil.example).
_GOOGLE_HOST_RE = re.compile(r"(^|\.)(google\.(?:com?\.)?[a-z]{2,3}|goo\.gl)$")
_MAX_PLACE_TEXT = 200


def extract_place_text_from_url(url: str) -> str | None:
    """The human-readable place text inside a Google Maps URL (the name and/or
    address in /maps/place/<text>/ or /maps/search/<text>, or a ?q= / ?query=
    parameter), cleaned up - or None. Only Google hosts: text lifted out of an
    arbitrary link is not something to hand to a geocoder."""
    parsed = urlparse(url)
    if not _GOOGLE_HOST_RE.search((parsed.hostname or "").lower()):
        return None

    candidates: list[str] = []
    query = parse_qs(parsed.query)
    for key in ("q", "query"):
        candidates.extend(query.get(key, []))
    match = _PLACE_PATH_RE.search(parsed.path)
    if match:
        candidates.append(unquote_plus(match.group(1)))

    for candidate in candidates:
        text = " ".join(_BIDI_CONTROLS_RE.sub("", candidate).split())[:_MAX_PLACE_TEXT]
        if text and not _COORD_PAIR_RE.fullmatch(text):
            return text
    return None


def _tidy_place_text(text: str | None) -> str | None:
    """Drops the trailing postcode Google adds - noise as a label, and
    geocode_candidates would strip it anyway."""
    if not text:
        return None
    return _POSTCODE_TAIL_RE.sub("", text).strip(" ,") or None


def resolve_maps_link_detail(text: str) -> tuple[tuple[float, float] | None, str | None]:
    """(coords, place_text) for pasted text. Coordinates come straight from the
    URL when it has them, otherwise from the expanded URL after following
    redirects (short links, maps.app.goo.gl, only reveal them once expanded).
    `place_text` is the place's name/address when the link carries one - the
    fallback to geocode when there are no coordinates, and a readable label
    for the location either way."""
    coords = extract_coords_from_url(text)
    if coords:
        return coords, _tidy_place_text(extract_place_text_from_url(text))

    if "http://" not in text and "https://" not in text:
        return None, None

    try:
        final_url = requests.get(text.strip(), timeout=5, allow_redirects=True).url
    except requests.RequestException:
        return None, _tidy_place_text(extract_place_text_from_url(text.strip()))
    return extract_coords_from_url(final_url), _tidy_place_text(
        extract_place_text_from_url(final_url) or extract_place_text_from_url(text.strip())
    )


def resolve_maps_link(text: str) -> tuple[float, float] | None:
    """Just the coordinates of resolve_maps_link_detail."""
    return resolve_maps_link_detail(text)[0]


def geocode_candidates(place_text: str) -> list[str]:
    """Queries to try, most to least specific, for a place's text from a link.
    Google writes "<name>, <address>, <city>, <postcode>" with its own
    transliteration of the street, which OpenStreetMap often doesn't have - so
    the full text can miss where the place's own name alone hits. Tried in
    order and stopped at the first hit, capped at three lookups. A geocoder
    can land on the wrong stretch of a long street, which is why the caller
    shows the matched text as the location's label for the person to check."""
    text = _POSTCODE_TAIL_RE.sub("", place_text).strip(" ,")
    parts = [part.strip() for part in text.split(",") if part.strip()]
    candidates: list[str] = []

    def add(candidate: str) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    add(text)
    if len(parts) > 1:
        add(parts[0])
    if len(parts) > 2:
        add(", ".join(parts[1:]))
    return candidates[:3]


# Nominatim's usage policy requires a real identifying User-Agent (not the
# default requests one) and caps usage at ~1 req/sec - not a concern at this
# app's personal-project volume, so no explicit throttling needed here.
_NOMINATIM_HEADERS = {"User-Agent": "tlv-bot (personal project - github.com/Nadavsim/tlv-whatsapp-map-bot)"}


class GeocodingUnavailable(Exception):
    """Nominatim couldn't answer (timeout, HTTP error like a 429, a malformed
    body) or we're deliberately backing off from it. Distinct from a query
    that simply has no match, which is a normal None result - the user
    should be told "try again", not "that address doesn't exist"."""


# An address's coordinates don't change, so a day is conservative - it just
# bounds how long an OpenStreetMap correction takes to show up. Only
# successful lookups are cached: a "no match" or a failure is cheap to retry
# and shouldn't stick around.
_geocode_cache = TTLCache(ttl_seconds=24 * 60 * 60, max_entries=1000)
_geocode_backoff = FailureBackoff(threshold=3, cooldown_seconds=30)


# The areas this app covers: Tel Aviv-Yafo (incl. Jaffa), Ramat Gan and
# Givatayim. An address anywhere else is "not found" rather than a same-named
# street in another city (Rothschild exists in Holon and Bat Yam too).
#
# Two layers, because neither alone is enough: the viewbox keeps the lookup to
# the right part of the country, but a rectangle around these three cities
# also contains Bnei Brak, Holon, Bat Yam, Kiryat Ono and Gan Shmuel - so every
# result's own municipality is checked against the allowlist as well. The box
# is deliberately a little generous; the allowlist is what decides.
_AREA_VIEWBOX = "34.73,32.15,34.87,32.01"  # lon,lat of two opposite corners


def _normalize_name(value: str) -> str:
    """Lowercased with everything but letters/digits removed, so Hebrew's
    non-ASCII hyphens and spacing variants (תל־אביב–יפו) compare equal."""
    return re.sub(r"[\W_]+", "", value.lower())


_ALLOWED_MUNICIPALITIES = {
    _normalize_name(name)
    for name in (
        "Tel Aviv-Yafo", "Tel Aviv", "Tel Aviv-Jaffa", "Jaffa", "Yafo",
        "תל אביב-יפו", "תל אביב", "יפו",
        "Ramat Gan", "רמת גן",
        "Givatayim", "Givataim", "גבעתיים",
    )
}
# If the person already typed one of these, adding "Tel Aviv-Yafo" would
# contradict them ("Jabotinsky 50 Ramat Gan, Tel Aviv-Yafo" found nothing).
_AREA_NAME_FRAGMENTS = tuple(_normalize_name(n) for n in ("Tel Aviv", "Jaffa", "Yafo", "Ramat Gan", "Givatayim", "Givataim", "תל אביב", "יפו", "רמת גן", "גבעתיים"))


def _names_an_area(text: str) -> bool:
    normalized = _normalize_name(text)
    return any(fragment in normalized for fragment in _AREA_NAME_FRAGMENTS)


def _municipality_is_in_area(result: dict) -> bool:
    """Nominatim reports the municipality as `city` for Tel Aviv and `town`
    for the others; a result without one is rejected rather than trusted."""
    address = result.get("address") or {}
    for key in ("city", "town", "municipality"):
        value = address.get(key)
        if value and _normalize_name(value) in _ALLOWED_MUNICIPALITIES:
            return True
    return False


def _search_area(query: str) -> tuple[float, float] | None:
    """One Nominatim lookup restricted to the area box; the first result
    whose municipality is allowed. Raises GeocodingUnavailable when it can't
    answer (and updates the back-off either way)."""
    params = {
        "q": query,
        "format": "json",
        "limit": 5,
        "countrycodes": "il",
        "addressdetails": 1,
        "viewbox": _AREA_VIEWBOX,
        "bounded": 1,
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
        found = next(
            ((float(r["lat"]), float(r["lon"])) for r in results if _municipality_is_in_area(r)),
            None,
        )
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError) as exc:
        _geocode_backoff.record_failure()
        raise GeocodingUnavailable("Nominatim request failed") from exc

    _geocode_backoff.record_success()
    return found


def geocode_address(text: str) -> tuple[float, float] | None:
    """Free-text address/landmark -> (lat, lon) via Nominatim (OpenStreetMap's
    free geocoder, no API key/billing), restricted to Tel Aviv-Yafo, Ramat Gan
    and Givatayim - see _AREA_VIEWBOX.

    Two passes. First the text with "Tel Aviv-Yafo" appended: plain "Tel Aviv"
    or no city is genuinely ambiguous in Israel, and without that bias
    "Rothschild 12" has no Tel Aviv result at all in the top five. If that
    finds nothing (a street that only exists in Ramat Gan or Givatayim), the
    text is tried as typed. Text that already names one of the areas skips the
    bias - appending Tel Aviv to "...Ramat Gan" was making those unfindable.

    Returns None when Nominatim answered but found nothing in the area.
    Raises GeocodingUnavailable when it couldn't answer at all."""
    cache_key = " ".join(text.lower().split())
    cached = _geocode_cache.get(cache_key)
    if cached is not None:
        return cached

    if _geocode_backoff.is_open():
        raise GeocodingUnavailable("backing off after repeated Nominatim failures")

    typed = text.strip()
    queries = [typed] if _names_an_area(typed) else [f"{typed}, Tel Aviv-Yafo", typed]
    coords = None
    for query in queries:
        coords = _search_area(query)
        if coords is not None:
            break

    if coords is not None:
        _geocode_cache.set(cache_key, coords)
    return coords
