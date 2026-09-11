from backend.parser import parse_kml_text

SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>TLV represent</name>
    <Folder>
      <name>Coffee</name>
      <Placemark>
        <name>Cafelix</name>
        <Point>
          <coordinates>34.7721282,32.0601551,0</coordinates>
        </Point>
      </Placemark>
      <Placemark>
        <name>Bucke</name>
        <description>Great flat white! https://www.instagram.com/bucke.tlv/ worth a visit</description>
        <Point>
          <coordinates>34.7691056,32.0580475,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
    <Folder>
      <name>Burger</name>
      <Placemark>
        <name>Meaty Place</name>
        <description>Solid burgers. #Kosher #Vegan-friendly #Kosher #$$</description>
        <Point>
          <coordinates>34.7748345,32.0817456,0</coordinates>
        </Point>
      </Placemark>
    </Folder>
  </Document>
</kml>
"""


def test_parses_all_placemarks_across_folders():
    places = parse_kml_text(SAMPLE_KML)
    assert len(places) == 3
    assert {p["name"] for p in places} == {"Cafelix", "Bucke", "Meaty Place"}


def test_category_comes_from_enclosing_folder_lowercased():
    places = parse_kml_text(SAMPLE_KML)
    by_name = {p["name"]: p for p in places}
    assert by_name["Cafelix"]["category"] == "coffee"
    assert by_name["Meaty Place"]["category"] == "burger"


def test_coordinates_parsed_as_lon_lat_from_kml_order():
    places = parse_kml_text(SAMPLE_KML)
    cafelix = next(p for p in places if p["name"] == "Cafelix")
    assert cafelix["longitude"] == 34.7721282
    assert cafelix["latitude"] == 32.0601551


def test_instagram_url_extracted_from_description_when_present():
    places = parse_kml_text(SAMPLE_KML)
    by_name = {p["name"]: p for p in places}
    assert by_name["Bucke"]["instagram_url"] == "https://www.instagram.com/bucke.tlv/"
    assert by_name["Cafelix"]["instagram_url"] is None


def test_placemark_outside_any_folder_is_skipped():
    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <name>Orphan</name>
          <Point><coordinates>34.77,32.08,0</coordinates></Point>
        </Placemark>
      </Document>
    </kml>
    """
    assert parse_kml_text(kml) == []


def test_placemark_in_nested_folder_is_counted_once_under_the_inner_category():
    # Google My Maps' own UI/export never nests folders (flat layer list), but
    # the parser shouldn't silently double-count a placemark if it ever did.
    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Folder>
          <name>Outer</name>
          <Folder>
            <name>Inner</name>
            <Placemark>
              <name>Nested Place</name>
              <Point><coordinates>34.77,32.08,0</coordinates></Point>
            </Placemark>
          </Folder>
        </Folder>
      </Document>
    </kml>
    """
    places = parse_kml_text(kml)
    assert len(places) == 1
    assert places[0]["category"] == "inner"


def test_dietary_tags_extracted_as_lowercased_deduped_hashtags():
    places = parse_kml_text(SAMPLE_KML)
    by_name = {p["name"]: p for p in places}
    assert by_name["Meaty Place"]["dietary_tags"] == ["kosher", "vegan"]


def test_dietary_tags_empty_when_no_hashtags_in_description():
    places = parse_kml_text(SAMPLE_KML)
    by_name = {p["name"]: p for p in places}
    assert by_name["Cafelix"]["dietary_tags"] == []
    assert by_name["Bucke"]["dietary_tags"] == []


def test_price_tier_extracted_from_dollar_hashtag():
    places = parse_kml_text(SAMPLE_KML)
    by_name = {p["name"]: p for p in places}
    assert by_name["Meaty Place"]["price_tier"] == "$$"


def test_price_tier_none_when_no_dollar_hashtag_in_description():
    places = parse_kml_text(SAMPLE_KML)
    by_name = {p["name"]: p for p in places}
    assert by_name["Cafelix"]["price_tier"] is None
    assert by_name["Bucke"]["price_tier"] is None


def test_price_tier_supports_one_to_three_dollar_signs():
    for tier in ("$", "$$", "$$$"):
        kml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
          <Document>
            <Folder>
              <name>Coffee</name>
              <Placemark>
                <name>Spot</name>
                <description>#{tier}</description>
                <Point><coordinates>34.77,32.08,0</coordinates></Point>
              </Placemark>
            </Folder>
          </Document>
        </kml>
        """
        places = parse_kml_text(kml)
        assert places[0]["price_tier"] == tier


def test_price_tier_rejected_when_more_than_three_dollar_signs():
    # Likely a typo - reject outright rather than silently truncate to "$$$".
    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Folder>
          <name>Coffee</name>
          <Placemark>
            <name>Spot</name>
            <description>#$$$$</description>
            <Point><coordinates>34.77,32.08,0</coordinates></Point>
          </Placemark>
        </Folder>
      </Document>
    </kml>
    """
    places = parse_kml_text(kml)
    assert places[0]["price_tier"] is None


def test_placemark_without_coordinates_is_skipped():
    kml = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Folder>
          <name>Coffee</name>
          <Placemark>
            <name>No Location</name>
          </Placemark>
        </Folder>
      </Document>
    </kml>
    """
    assert parse_kml_text(kml) == []
