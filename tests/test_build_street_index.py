import json
from datetime import date

from scripts import build_street_index as build


def test_extract_names_collects_hebrew_and_english_sorted_and_deduplicated():
    elements = [
        {"tags": {"name": "דיזנגוף", "name:en": "Dizengoff Street"}},
        {"tags": {"name": "דיזנגוף", "name:en": "Dizengoff Street"}},  # another way, same street
        {"tags": {"name": "אלנבי"}},  # no English name
        {"tags": {"name:en": "Allenby Street"}},  # no local name
    ]

    hebrew, english = build.extract_names(elements)

    assert hebrew == sorted(["דיזנגוף", "אלנבי"])
    assert english == ["Allenby Street", "Dizengoff Street"]


def test_extract_names_normalizes_whitespace_and_drops_non_names():
    elements = [
        {"tags": {"name": "  Ben   Yehuda  ", "name:en": "Ben Yehuda"}},
        {"tags": {"name": "12"}},  # no letters at all
        {"tags": {"name": ""}},
        {"tags": {"name": None}},
        {"tags": {}},
        {},
    ]

    hebrew, english = build.extract_names(elements)

    assert hebrew == ["Ben Yehuda"]
    assert english == ["Ben Yehuda"]


def test_build_document_carries_attribution_license_and_counts():
    doc = build.build_document(["a b"], ["c d", "e f"])

    assert doc["_meta"]["attribution"] == "© OpenStreetMap contributors"
    assert "ODbL" in doc["_meta"]["license"]
    assert doc["_meta"]["counts"] == {"he": 1, "en": 2}
    assert doc["_meta"]["generated"] == date.today().isoformat()
    assert doc["he"] == ["a b"] and doc["en"] == ["c d", "e f"]
    json.dumps(doc, ensure_ascii=False)  # serialisable


def test_bbox_matches_the_geocoders_area_box():
    # Same area on purpose: streets outside it would never resolve anyway,
    # and a wider list would only add false matches.
    from backend.services import location

    west, north, east, south = (float(v) for v in location._AREA_VIEWBOX.split(",")[0:4])
    south_b, west_b, north_b, east_b = build.BBOX
    assert (south_b, west_b, north_b, east_b) == (south, west, north, east)
