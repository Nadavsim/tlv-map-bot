import json

import pytest

from backend.services import streets

# Hebrew spellings built from escapes so the file reads the same in any editor.
DIZENGOFF_HE = "דיזנגוף"
DIZENGOK_HE = "דיזנגוק"  # last letter wrong
ROTHSCHILD_HE = "רוטששילד"


@pytest.fixture
def small_index(monkeypatch):
    """A tiny, fixed street list so matcher behavior doesn't depend on the
    shipped data (which is tested separately below)."""
    indexes = {
        "en": streets._Index(
            [
                "Dizengoff Street",
                "Dizengoff Square",
                "Rothschild Boulevard",
                "Allenby Street",
                "Ben Yehuda Street",
                "Ibn Gabirol Street",
                "Jabotinsky Street",
                "Bialik Street",
                "Ha'Yarkon Street",
                "Kikar Rabin",
            ]
        ),
        "he": streets._Index([DIZENGOFF_HE, ROTHSCHILD_HE]),
    }
    monkeypatch.setattr(streets, "_indexes", indexes)
    return indexes


@pytest.mark.parametrize(
    "typed,expected",
    [
        ("Dizengoeff 50", "Dizengoff 50"),
        ("dizingof 50", "Dizengoff 50"),
        ("rotschild 12", "Rothschild 12"),
        ("Ibn Gvirol 67", "Ibn Gabirol 67"),
        ("Zabotinsky 50", "Jabotinsky 50"),
        ("Bialek 10", "Bialik 10"),
        # The house number can come first.
        ("50 dizingof", "50 Dizengoff"),
    ],
)
def test_corrects_a_misspelt_street_and_keeps_the_house_number(small_index, typed, expected):
    assert streets.suggest_correction(typed) == expected


def test_keeps_generic_words_exactly_as_typed(small_index):
    assert streets.suggest_correction("Dizengoeff square") == "Dizengoff square"
    assert streets.suggest_correction("Dizengoeff St 12") == "Dizengoff St 12"
    assert streets.suggest_correction("Rothchild Blvd 20") == "Rothschild Blvd 20"


def test_keeps_a_trailing_city_as_typed(small_index):
    assert streets.suggest_correction("dizingof 50, Ramat Gan") == "Dizengoff 50, Ramat Gan"
    assert streets.suggest_correction("dizingof 50 Tel Aviv") == "Dizengoff 50 Tel Aviv"


def test_corrects_hebrew_against_hebrew_names(small_index):
    assert streets.suggest_correction(f"{DIZENGOK_HE} 50") == f"{DIZENGOFF_HE} 50"


@pytest.mark.parametrize(
    "typed", ["Dizengoff 50", "Rothschild 12", "Dizengoff Square", "Allenby 20", "Jabotinsky 50, Ramat Gan"]
)
def test_a_correctly_spelt_street_needs_no_suggestion(small_index, typed):
    # The lookup failed for some other reason (no such number, etc.) - there is
    # nothing to "correct", and inventing a different street would mislead.
    assert streets.suggest_correction(typed) is None


@pytest.mark.parametrize(
    "typed",
    [
        "asdkfjh",  # junk
        "pizza",
        "the shuk",
        "Herzl 1 Haifa",  # another city's street
        "New York 5",
        "50",  # a number alone
        "",
        "   ",
        "ab",  # too short to mean anything
    ],
)
def test_no_close_street_means_no_suggestion(small_index, typed):
    assert streets.suggest_correction(typed) is None


def test_short_names_need_a_closer_match(small_index):
    # "home" is within the normal cutoff of "ha omer"-like names in the real
    # data; short names are held to a stricter ratio (see SHORT_NAME_CUTOFF).
    monkey = streets._Index(["HaOmer Street"])
    streets._indexes["en"] = monkey
    assert streets.suggest_correction("home") is None


def test_very_long_or_many_word_input_is_ignored(small_index):
    assert streets.suggest_correction("x" * 200) is None
    assert streets.suggest_correction("one two three four five six dizingof 50") is None


def test_missing_data_file_degrades_to_no_suggestions(monkeypatch, tmp_path):
    monkeypatch.setattr(streets, "_indexes", None)
    monkeypatch.setattr(streets, "DATA_PATH", tmp_path / "nope.json")

    assert streets.suggest_correction("dizingof 50") is None


def test_malformed_data_file_degrades_to_no_suggestions(monkeypatch, tmp_path):
    bad = tmp_path / "streets.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(streets, "_indexes", None)
    monkeypatch.setattr(streets, "DATA_PATH", bad)

    assert streets.suggest_correction("dizingof 50") is None


# --- the data file that actually ships --------------------------------------


@pytest.fixture
def real_index(monkeypatch):
    monkeypatch.setattr(streets, "_indexes", None)  # force a load of the shipped file


@pytest.mark.parametrize(
    "typed,expected",
    [
        ("dizingof 50", "Dizengoff 50"),
        ("Allenbi 20", "Allenby 20"),
        ("Ben Yeuda 100", "Ben Yehuda 100"),
        ("Ibn Gvirol 67", "Ibn Gabirol 67"),
        ("Zabotinsky 50", "Jabotinsky 50"),
        (f"{DIZENGOK_HE} 50", f"{DIZENGOFF_HE} 50"),
    ],
)
def test_shipped_street_data_corrects_real_typos(real_index, typed, expected):
    assert streets.suggest_correction(typed) == expected


@pytest.mark.parametrize("typed", ["Dizengoff 50", "Rothschild 12", "Allenby 20", "Bialik 10"])
def test_shipped_street_data_leaves_valid_streets_alone(real_index, typed):
    assert streets.suggest_correction(typed) is None


def test_shipped_file_is_complete_and_carries_its_attribution():
    data = json.loads(streets.DATA_PATH.read_text(encoding="utf-8"))

    assert len(data["he"]) > 1000 and len(data["en"]) > 1000
    meta = data["_meta"]
    # The ODbL requires attribution - it must travel with the data.
    assert "OpenStreetMap" in meta["attribution"]
    assert "ODbL" in meta["license"]
    assert meta["counts"] == {"he": len(data["he"]), "en": len(data["en"])}
