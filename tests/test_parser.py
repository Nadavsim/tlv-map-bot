from parser import parse_kml_text

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
