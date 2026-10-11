"""Offers a corrected spelling for a mistyped street address.

The geocoder has no fuzzy matching ("Dizengoeff 50" finds nothing, though
"Dizengoff 50" is fine), so when a lookup fails this compares the typed street
against the street names of Tel Aviv-Yafo, Ramat Gan and Givatayim - a list
generated from OpenStreetMap by scripts/build_street_index.py and shipped with
the app. Free, instant, and nothing about the address leaves the server.

It only ever *suggests*: the caller shows the correction to the person and
they confirm it, because a wrong silent correction is worse than a not-found.
"""

import difflib
import json
import re
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "streets.json"

# difflib's ratio: 1.0 is identical. Measured on real typos (dizingof,
# Allenbi, Ibn Gvirol, Zabotinsky, Hebrew letter swaps) and on look-alike
# non-streets; below this, ordinary words started matching real streets.
MATCH_CUTOFF = 0.8
# Anything shorter is too little signal to call a "correction" - one wrong
# letter in a three-letter name is a different name, not a typo.
MIN_CORE_LENGTH = 4
# Short names get a stricter match: with few letters, ordinary words ("home",
# "here", "mall") land within the normal cutoff of some real street.
SHORT_NAME_LENGTH = 6
SHORT_NAME_CUTOFF = 0.88
MAX_INPUT_LENGTH = 100

# Words that are part of how a street is written rather than its name. They
# are ignored when comparing and kept exactly as typed in the result, so
# "Dizengoeff square" comes back as "Dizengoff square".
_GENERIC_WORDS = {
    "street", "st", "str", "road", "rd", "boulevard", "blvd", "avenue", "ave",
    "square", "sq", "alley", "lane", "way", "junction", "kikar", "rehov",
    "sderot", "derech", "simtat", "sderet",
    "רחוב", "רח", "שדרות", "שד", "כיכר", "סמטת", "דרך", "שדרת", "מעלה",
}
# The city, when typed without a comma ("dizingof 50 tel aviv"), is not part
# of the street; it is set aside and appended back unchanged.
_AREA_PHRASES = (
    "tel aviv-yafo", "tel aviv yafo", "tel aviv", "tel-aviv", "ramat gan", "ramat-gan",
    "givatayim", "givataim", "jaffa", "yafo",
    "תל אביב-יפו", "תל אביב יפו", "תל אביב", "תל-אביב", "רמת גן", "רמת-גן", "גבעתיים", "יפו",
)
_AREA_RE = re.compile(
    r"(?<![\w])(?:" + "|".join(re.escape(p) for p in sorted(_AREA_PHRASES, key=len, reverse=True)) + r")(?![\w])",
    re.IGNORECASE,
)
_NUMBER_TOKEN_RE = re.compile(r"^\d{1,4}[a-zא-ת]?$", re.IGNORECASE)
_HEBREW_RE = re.compile(r"[֐-׿]")


def _key(value: str) -> str:
    """Comparison form: lowercase, apostrophe/geresh variants dropped,
    punctuation to spaces, whitespace collapsed."""
    value = re.sub(r"[׳״'’`\"]", "", value.lower())
    value = re.sub(r"[^\w\s]|_", " ", value)
    return " ".join(value.split())


def _is_generic(token: str) -> bool:
    return _key(token) in _GENERIC_WORDS


def _core(name: str) -> str:
    """A street's name without the generic words around it."""
    tokens = [t for t in name.split() if not _is_generic(t)]
    return " ".join(tokens) if tokens else name


class _Index:
    def __init__(self, names: list[str]):
        # comparison key -> a display spelling (first one seen wins)
        self.display: dict[str, str] = {}
        for name in names:
            core = _core(name)
            key = _key(core)
            if len(key) >= MIN_CORE_LENGTH and key not in self.display:
                self.display[key] = core
        self.keys = list(self.display)


_indexes: dict[str, _Index] | None = None


def _load_indexes() -> dict[str, _Index]:
    global _indexes
    if _indexes is None:
        try:
            data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            _indexes = {"he": _Index(data.get("he", [])), "en": _Index(data.get("en", []))}
        except (OSError, ValueError):
            # No data file means no suggestions, never a failed lookup.
            _indexes = {"he": _Index([]), "en": _Index([])}
    return _indexes


def suggest_correction(text: str) -> str | None:
    """A corrected spelling of `text`, or None if it needs none / has no close
    street. The house number, generic words and any trailing city are kept
    exactly as typed; only the street's own name is replaced."""
    typed = " ".join(text.split())
    if not typed or len(typed) > MAX_INPUT_LENGTH:
        return None

    # Anything after the first comma is the city/extra detail: set aside.
    head, comma, tail = typed.partition(",")
    suffix = f"{comma}{tail}" if comma else ""
    areas = _AREA_RE.findall(head)
    if areas:
        head = " ".join(_AREA_RE.sub(" ", head).split())
        suffix = f" {' '.join(areas)}{suffix}"

    tokens = head.split()
    # The street's own name: tokens that are neither a house number nor a
    # generic word, as one contiguous run (a number or "St" sits around it).
    name_positions = [
        i for i, t in enumerate(tokens) if not _NUMBER_TOKEN_RE.match(t) and not _is_generic(t)
    ]
    if not name_positions or name_positions[-1] - name_positions[0] + 1 != len(name_positions):
        return None
    first, last = name_positions[0], name_positions[-1]
    if len(name_positions) > 4:
        return None

    typed_name = " ".join(tokens[first : last + 1])
    key = _key(typed_name)
    if len(key) < MIN_CORE_LENGTH:
        return None

    index = _load_indexes()["he" if _HEBREW_RE.search(typed_name) else "en"]
    if key in index.display:
        return None  # a real street already - the failure is something else
    cutoff = SHORT_NAME_CUTOFF if len(key) < SHORT_NAME_LENGTH else MATCH_CUTOFF
    matches = difflib.get_close_matches(key, index.keys, n=1, cutoff=cutoff)
    if not matches:
        return None

    corrected_tokens = tokens[:first] + [index.display[matches[0]]] + tokens[last + 1 :]
    return " ".join(corrected_tokens) + suffix
