from datetime import datetime, timezone

from scripts import show_suggestions as script

WHEN = datetime(2026, 10, 27, 9, 30, tzinfo=timezone.utc)


def _item(**overrides):
    base = {
        "_id": "id1",
        "place_text": "Cafe Xoho",
        "category": "coffee",
        "link": None,
        "name": "Dana",
        "status": "new",
        "created_at": WHEN,
        "lat": None,
        "lon": None,
    }
    return {**base, **overrides}


def test_safe_removes_control_and_escape_characters():
    assert script.safe("red " + chr(27) + "[31mtext") == "red [31mtext"
    assert script.safe("a\x00b\nc\td") == "a b c d"
    assert script.safe("rtl" + chr(0x202E) + "override") == "rtl override"
    assert script.safe("x" * 500) == "x" * 300
    assert script.safe(None) == "?"


def test_rows_show_name_category_who_and_when():
    rows = script.build_rows([_item()], {})

    assert rows == [
        {
            "id": "id1",
            "what": "Cafe Xoho",
            "category": "coffee",
            "link": "",
            "who": "Dana",
            "when": "2026-10-27",
            "status": "new",
            "already": "",
        }
    ]


def test_a_link_without_a_name_says_to_open_it():
    rows = script.build_rows([_item(place_text=None, link="https://maps.app.goo.gl/abc")], {})

    assert rows[0]["what"] == "(no name found - open the link)"
    assert rows[0]["link"] == "https://maps.app.goo.gl/abc"


def test_a_suggestion_near_an_existing_place_is_flagged():
    rows = script.build_rows([_item(lat=32.07, lon=34.77)], {"id1": {"name": "Cafelix", "category": "coffee"}})

    assert rows[0]["already"] == "Cafelix (coffee)"
    assert "ALREADY ON THE MAP as Cafelix (coffee)" in script.format_row(rows[0])


def test_the_email_appears_only_when_asked_for():
    item = _item(email="dana@example.com")

    assert "email" not in script.build_rows([item], {})[0]
    with_email = script.build_rows([item], {}, include_email=True)[0]
    assert with_email["email"] == "dana@example.com"
    assert "contact: dana@example.com" in script.format_row(with_email)
    assert "dana@example.com" not in script.format_row(script.build_rows([item], {})[0])


def test_a_deleted_account_is_labelled():
    assert script.build_rows([_item(name=None)], {})[0]["who"] == "(account deleted)"


def test_stored_escape_sequences_never_reach_the_terminal():
    nasty = _item(place_text="evil " + chr(27) + "]0;owned" + chr(7), name="x" + chr(27) + "[2J")
    rendered = script.format_row(script.build_rows([nasty], {})[0])

    assert chr(27) not in rendered and chr(7) not in rendered


def test_rows_for_closed_suggestions_show_their_status():
    assert "status: added" in script.format_row(script.build_rows([_item(status="added")], {})[0])
