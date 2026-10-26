"""What a signed-in visitor may submit when suggesting a spot, made safe to store.

Everything a visitor types is reduced to plain text here, on the server, before
it reaches the database. The only reader of a suggestion is the curator's
terminal script (nothing is ever returned to other visitors and the React UI
never renders HTML from user data), so the aim is two layers of defence: no
markup or control/escape characters stored, and the script cleans its output
once more.
"""

import re
from urllib.parse import urlparse

from . import location

MAX_PLACE_CHARS = 300
OTHER_CATEGORY = "other"
MAX_CATEGORY_CHARS = 40

_TAG_RE = re.compile(r"<[^<>]*>")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def clean_text(raw: object, max_len: int = MAX_PLACE_CHARS) -> str:
    """Plain text only: HTML tags removed, any leftover angle brackets dropped,
    control characters (including terminal escape sequences) and invisible
    bidi/zero-width characters replaced by spaces, whitespace collapsed, length
    capped. Non-strings become ''."""
    if not isinstance(raw, str):
        return ""
    text = raw
    # Tags can nest ("<<b>script>"), so strip until nothing changes.
    for _ in range(5):
        stripped = _TAG_RE.sub(" ", text)
        if stripped == text:
            break
        text = stripped
    text = text.replace("<", " ").replace(">", " ")
    # str.isprintable() is False for control characters and for format
    # characters such as bidi marks and the zero-width space alike.
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    return " ".join(text.split())[:max_len]


def extract_link(text: str) -> str | None:
    """The first http(s) URL in already-cleaned text, if any."""
    match = _URL_RE.search(text)
    return match.group(0).rstrip(".,;)") if match else None


def is_google_link(url: str) -> bool:
    return location._is_google_url(url)


def place_key(place_text: str | None, coords: tuple[float, float] | None) -> str:
    """What makes two suggestions "the same place" for one person: the rounded
    coordinates when the link gave any, otherwise the name, case-folded."""
    if coords:
        return f"{coords[0]:.4f},{coords[1]:.4f}"
    return " ".join((place_text or "").casefold().split())


def display_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()
