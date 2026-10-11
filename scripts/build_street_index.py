"""Builds backend/data/streets.json - the street names of Tel Aviv-Yafo, Ramat
Gan and Givatayim that services/streets.py fuzzy-matches a mistyped address
against ("Dizengoeff 50" -> "Dizengoff 50").

Run it by hand, rarely - street names barely change:

    python -m scripts.build_street_index

Source: OpenStreetMap, via the free Overpass API (one query, a few seconds).
The data is (c) OpenStreetMap contributors, licensed ODbL 1.0 - the file
carries that attribution in its own header, keep it there.
"""

import json
import time
from datetime import date
from pathlib import Path

import requests

# Same rectangle as services/location._AREA_VIEWBOX (south, west, north, east
# is Overpass's order). A little generous on purpose: matching a street that
# merely runs near the border costs nothing, the geocoder's own area check
# still decides whether the final address counts.
BBOX = (32.01, 34.73, 32.15, 34.87)
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "backend" / "data" / "streets.json"
USER_AGENT = "tlv-bot (personal project - github.com/Nadavsim/tlv-whatsapp-map-bot)"


def extract_names(elements: list[dict]) -> tuple[list[str], list[str]]:
    """(hebrew_names, english_names), each sorted and de-duplicated, from
    Overpass `way` elements. `name` is OpenStreetMap's local (Hebrew) name,
    `name:en` the English one; either may be missing. Entries with no letter
    in them are dropped - they can't be a street someone types."""

    def usable(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        value = " ".join(value.split())
        return value if any(ch.isalpha() for ch in value) else None

    hebrew: set[str] = set()
    english: set[str] = set()
    for element in elements:
        tags = element.get("tags") or {}
        if name := usable(tags.get("name")):
            hebrew.add(name)
        if name_en := usable(tags.get("name:en")):
            english.add(name_en)
    return sorted(hebrew), sorted(english)


def build_document(hebrew: list[str], english: list[str]) -> dict:
    return {
        "_meta": {
            "source": "OpenStreetMap via the Overpass API",
            "attribution": "© OpenStreetMap contributors",
            "license": "ODbL 1.0 - https://opendatacommons.org/licenses/odbl/1-0/",
            "generated": date.today().isoformat(),
            "bbox_south_west_north_east": list(BBOX),
            "counts": {"he": len(hebrew), "en": len(english)},
            "generator": "scripts/build_street_index.py",
        },
        "he": hebrew,
        "en": english,
    }


def fetch_elements() -> list[dict]:
    south, west, north, east = BBOX
    query = f'[out:json][timeout:90];way["highway"]["name"]({south},{west},{north},{east});out tags;'
    # The public Overpass instances shed load with 429/504 now and then - a
    # one-off script is allowed to simply wait and try again.
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            response = requests.post(
                OVERPASS_URL, data={"data": query}, timeout=120, headers={"User-Agent": USER_AGENT}
            )
            response.raise_for_status()
            return response.json()["elements"]
        except requests.RequestException as exc:
            last_error = exc
            print(f"Overpass attempt {attempt} failed ({exc}); retrying...")
            time.sleep(10 * attempt)
    raise SystemExit(f"Overpass kept failing: {last_error}")


def main() -> None:
    hebrew, english = extract_names(fetch_elements())
    # A truncated or empty answer would silently turn the feature off - refuse
    # to overwrite a good file with one.
    if len(hebrew) < 1000 or len(english) < 1000:
        raise SystemExit(f"Suspiciously small result ({len(hebrew)} he / {len(english)} en) - not writing.")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = build_document(hebrew, english)
    OUTPUT_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} - {len(hebrew)} Hebrew and {len(english)} English street names.")


if __name__ == "__main__":
    main()
