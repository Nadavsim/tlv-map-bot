from db import build_geo_pipeline


def test_geo_pipeline_uses_geojson_lon_lat_order():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3)
    near = pipeline[0]["$geoNear"]["near"]
    assert near["type"] == "Point"
    assert near["coordinates"] == [34.78, 32.08]


def test_geo_pipeline_filters_by_category():
    pipeline = build_geo_pipeline("burger", lat=32.08, lon=34.78, limit=3)
    assert pipeline[0]["$geoNear"]["query"] == {"category": "burger"}


def test_geo_pipeline_respects_limit():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=5)
    assert pipeline[1] == {"$limit": 5}


def test_geo_pipeline_is_spherical():
    pipeline = build_geo_pipeline("coffee", lat=32.08, lon=34.78, limit=3)
    assert pipeline[0]["$geoNear"]["spherical"] is True
