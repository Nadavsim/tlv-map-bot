import pytest

from backend.services import suggestions


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Cafe Xoho", "Cafe Xoho"),
        ("  spaced    out  ", "spaced out"),
        ("<script>alert(1)</script>", "alert(1)"),
        ("<b>bold</b> place", "bold place"),
        ("<<b>script>evil<</b>/script>", "evil"),
        ("a < b > c", "a c"),
        ('<img src=x onerror="steal()">Cafe', "Cafe"),
        ("line1\nline2\ttab", "line1 line2 tab"),
        ("red " + chr(27) + "[31mtext", "red [31mtext"),
        ("null" + chr(0) + "byte", "null byte"),
        ("hebrew רק\"ל kept", "hebrew רק\"ל kept"),
        ("rtl" + chr(0x202E) + "override", "rtl override"),
        ("zero" + chr(0x200B) + "width", "zero width"),
        ("x" * 500, "x" * 300),
        ("", ""),
        ("   ", ""),
        (None, ""),
        (42, ""),
        (["a"], ""),
        ({"$ne": 1}, ""),
    ],
)
def test_clean_text_reduces_anything_to_plain_text(raw, expected):
    assert suggestions.clean_text(raw) == expected


def test_clean_text_honours_a_shorter_cap():
    assert suggestions.clean_text("abcdefghij", 4) == "abcd"


def test_clean_text_never_leaves_an_angle_bracket():
    for raw in ("<", ">", "<<<>>>", "a<b", "<a href='x'>y</a>", "&lt;script&gt;"):
        assert "<" not in suggestions.clean_text(raw)
        assert ">" not in suggestions.clean_text(raw)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://maps.app.goo.gl/abc123", "https://maps.app.goo.gl/abc123"),
        ("try https://maps.app.goo.gl/abc123.", "https://maps.app.goo.gl/abc123"),
        ("(https://www.google.com/maps/place/X)", "https://www.google.com/maps/place/X"),
        ("Cafe Xoho", None),
        ("", None),
    ],
)
def test_extract_link(text, expected):
    assert suggestions.extract_link(text) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://maps.app.goo.gl/abc123", True),
        ("https://www.google.com/maps/place/X", True),
        ("https://www.google.co.il/maps", True),
        ("https://evil.example/maps", False),
        ("https://google.com.evil.example/", False),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("javascript:alert(1)", False),
        ("ftp://www.google.com/x", False),
    ],
)
def test_only_google_links_are_accepted(url, expected):
    assert suggestions.is_google_link(url) is expected


def test_place_key_prefers_rounded_coordinates_then_the_folded_name():
    assert suggestions.place_key("Anything", (32.077958, 34.774204)) == "32.0780,34.7742"
    assert suggestions.place_key("  Cafe   XOHO ", None) == "cafe xoho"
    assert suggestions.place_key(None, None) == ""
