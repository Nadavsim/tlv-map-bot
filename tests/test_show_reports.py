from datetime import datetime, timezone

from scripts.show_reports import build_rows, format_rows


def _report(place_id, kind, count, day, name="Old name", category="coffee"):
    return {
        "place_id": place_id,
        "kind": kind,
        "count": count,
        "last_at": datetime(2026, 10, day, tzinfo=timezone.utc),
        "name": name,
        "category": category,
    }


def test_most_reported_first_with_the_places_current_name():
    reports = [
        _report("a", "closed", 1, 10),
        _report("b", "closed", 4, 9),
    ]
    places = {"a": {"name": "A now", "category": "coffee"}, "b": {"name": "B now", "category": "coffee"}}

    rows = build_rows(reports, places)

    assert [r["name"] for r in rows] == ["B now", "A now"]


def test_flags_a_place_that_is_no_longer_on_the_map():
    rows = build_rows([_report("gone", "closed", 2, 10, name="Snapshot name")], {})

    assert rows[0]["name"] == "Snapshot name"
    assert rows[0]["note"] == "no longer on the map"


def test_flags_a_category_that_changed_since_the_report():
    rows = build_rows(
        [_report("a", "wrong_category", 1, 10, category="coffee")],
        {"a": {"name": "A", "category": "bakery"}},
    )

    assert rows[0]["note"] == "category is now bakery"


def test_a_closed_report_has_no_category_note():
    rows = build_rows([_report("a", "closed", 1, 10)], {"a": {"name": "A", "category": "bakery"}})

    assert rows[0]["note"] == ""


def test_format_rows():
    rows = build_rows([_report("a", "closed", 3, 10)], {"a": {"name": "Cafelix", "category": "coffee"}})

    text = format_rows(rows)

    assert "3x" in text and "closed" in text and "Cafelix (coffee)" in text and "last 2026-10-10" in text
    assert "id=a" in text


def test_endorsements_get_their_own_section_after_the_problems():
    reports = [
        _report("a", "would_return", 5, 10),
        _report("b", "closed", 1, 10),
    ]
    places = {"a": {"name": "Loved", "category": "coffee"}, "b": {"name": "Shut", "category": "coffee"}}

    text = format_rows(build_rows(reports, places))

    assert text.index("Problems") < text.index("Shut") < text.index("Would go back") < text.index("Loved")
    assert "would go back" in text


def test_format_rows_when_empty():
    assert format_rows([]) == "No reports."
