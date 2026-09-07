import pytest
from pydantic import ValidationError

from backend.models import GeoPoint, Place, PlaceResult


def test_geo_point_exposes_longitude_and_latitude_from_geojson_order():
    point = GeoPoint(coordinates=(34.7739, 32.0653))
    assert point.longitude == 34.7739
    assert point.latitude == 32.0653


def test_geo_point_defaults_type_to_point():
    point = GeoPoint(coordinates=(34.7739, 32.0653))
    assert point.type == "Point"


def test_place_requires_name_category_and_location():
    with pytest.raises(ValidationError):
        Place(category="coffee", location=GeoPoint(coordinates=(34.77, 32.06)))


def test_place_instagram_url_and_last_synced_at_default_to_none():
    place = Place(name="Cafelix", category="coffee", location=GeoPoint(coordinates=(34.77, 32.06)))
    assert place.instagram_url is None
    assert place.last_synced_at is None


def test_place_ignores_unknown_fields_like_mongo_id():
    place = Place(
        name="Cafelix",
        category="coffee",
        location=GeoPoint(coordinates=(34.77, 32.06)),
        _id="507f1f77bcf86cd799439011",
    )
    assert not hasattr(place, "_id")


def test_place_result_adds_distance_on_top_of_place_fields():
    result = PlaceResult(
        name="Cafelix",
        category="coffee",
        location=GeoPoint(coordinates=(34.77, 32.06)),
        distance=123.4,
    )
    assert result.distance == 123.4
    assert result.name == "Cafelix"


def test_place_result_requires_distance():
    with pytest.raises(ValidationError):
        PlaceResult(name="Cafelix", category="coffee", location=GeoPoint(coordinates=(34.77, 32.06)))
