import re
import xml.etree.ElementTree as ET

# My Maps' public KML export doesn't include a <description> per pin by default,
# but if the user ever adds one (e.g. pastes an Instagram link into a pin's
# description in the My Maps UI), pull it out automatically.
_NS = {"kml": "http://www.opengis.net/kml/2.2"}
_INSTAGRAM_RE = re.compile(r"https?://(?:www\.)?instagram\.com/\S+", re.IGNORECASE)

# Dietary/other tags are hashtags typed into the same pin description field
# (e.g. "#kosher #vegan") - deliberately free-form (whatever hashtag is
# typed becomes a real, queryable tag) rather than a fixed/validated set,
# mirroring how categories are just whatever a My Maps layer is named
# rather than a hardcoded list. Doesn't compete with the ~10-layer cap
# already spent on categories, since no new layers are needed.
_TAG_RE = re.compile(r"#(\w+)", re.UNICODE)

# Price tier, typed into the same description field as "#$$" - kept separate
# from _TAG_RE/dietary_tags rather than folded in: "$" isn't a \w character
# (so it wouldn't match _TAG_RE anyway), and a place has exactly one price
# tier, not an open set of them like dietary tags. The negative lookahead
# caps it at 1-3 signs - "#$$$$" (a likely typo) is rejected outright rather
# than silently truncated to "$$$".
_PRICE_RE = re.compile(r"#(\${1,3})(?!\$)")


def parse_kml_text(kml_text: str) -> list[dict]:
    """Parse KML text (My Maps export) into a list of place dicts.

    Each dict has: name, category, latitude, longitude, instagram_url (may
    be None), dietary_tags (list[str], may be empty), price_tier (one of
    "$"/"$$"/"$$$", may be None). 'category' comes from the enclosing
    Folder name (My Maps layers).
    """
    root = ET.fromstring(kml_text)
    places_data = []

    for folder in root.findall(".//kml:Folder", _NS):
        folder_name_node = folder.find("kml:name", _NS)
        category_name = (
            folder_name_node.text
            if folder_name_node is not None and folder_name_node.text
            else "Uncategorized"
        )

        # Direct children only - ".//" would also match placemarks belonging
        # to a nested sub-folder (if one ever existed) and double-count them
        # under both the outer and inner folder's category.
        for placemark in folder.findall("kml:Placemark", _NS):
            place_name_node = placemark.find("kml:name", _NS)
            place_name = (
                place_name_node.text
                if place_name_node is not None and place_name_node.text
                else "Unknown"
            )

            coords_node = placemark.find(".//kml:coordinates", _NS)
            if coords_node is None or coords_node.text is None:
                continue

            coords = coords_node.text.strip().split(",")
            if len(coords) < 2:
                continue

            longitude = float(coords[0])
            latitude = float(coords[1])

            instagram_url = None
            dietary_tags: list[str] = []
            price_tier = None
            desc_node = placemark.find("kml:description", _NS)
            if desc_node is not None and desc_node.text:
                match = _INSTAGRAM_RE.search(desc_node.text)
                if match:
                    instagram_url = match.group(0)
                dietary_tags = sorted({tag.lower() for tag in _TAG_RE.findall(desc_node.text)})
                price_match = _PRICE_RE.search(desc_node.text)
                if price_match:
                    price_tier = price_match.group(1)

            places_data.append(
                {
                    "name": place_name.strip(),
                    "category": category_name.strip().lower(),
                    "latitude": latitude,
                    "longitude": longitude,
                    "instagram_url": instagram_url,
                    "dietary_tags": dietary_tags,
                    "price_tier": price_tier,
                }
            )

    return places_data


def parse_kml_file(kml_file_path: str) -> list[dict]:
    with open(kml_file_path, encoding="utf-8") as f:
        return parse_kml_text(f.read())


if __name__ == "__main__":
    # Convenience for local/offline use: parse a manually-exported KML file
    # instead of fetching one over the network.
    places = parse_kml_file("data/map.kml")
    print(f"Parsed {len(places)} places from data/map.kml")
    for p in places[:5]:
        print(p)
