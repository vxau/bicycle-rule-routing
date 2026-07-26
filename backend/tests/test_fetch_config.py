import pytest
import geopandas as gpd
from shapely.geometry import LineString

from backend.scripts.fetch_osm_sample import (
    parse_fetch_config,
    prepare_geojson_frame,
)


def test_parse_fetch_config_accepts_valid_values() -> None:
    config = parse_fetch_config(
        {
            "OSM_CENTER_LAT": "35.681236",
            "OSM_CENTER_LON": "139.767125",
            "OSM_DISTANCE_METERS": "500",
            "OSM_PLACE_LABEL": "Tokyo Station",
        }
    )

    assert config.latitude == 35.681236
    assert config.longitude == 139.767125
    assert config.distance_m == 500
    assert config.place_label == "Tokyo Station"


@pytest.mark.parametrize(
    "override",
    [
        {"OSM_CENTER_LAT": "91"},
        {"OSM_CENTER_LON": "-181"},
        {"OSM_DISTANCE_METERS": "99"},
        {"OSM_DISTANCE_METERS": "5001"},
    ],
)
def test_parse_fetch_config_rejects_out_of_range_values(
    override: dict[str, str],
) -> None:
    values = {
        "OSM_CENTER_LAT": "35.681236",
        "OSM_CENTER_LON": "139.767125",
        "OSM_DISTANCE_METERS": "500",
        "OSM_PLACE_LABEL": "Tokyo Station",
        **override,
    }

    with pytest.raises(ValueError):
        parse_fetch_config(values)


def test_prepare_geojson_frame_serializes_list_attributes() -> None:
    frame = gpd.GeoDataFrame(
        {"cycleway": [["lane", "track"]]},
        geometry=[LineString([(0, 0), (1, 1)])],
        crs="EPSG:4326",
    )

    prepared = prepare_geojson_frame(frame)

    assert prepared.loc[0, "cycleway"] == '["lane", "track"]'
    assert prepared.geometry.name == "geometry"
