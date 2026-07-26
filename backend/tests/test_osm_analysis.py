import geopandas as gpd
import pytest
from shapely.geometry import LineString

from backend.app.osm_analysis import (
    build_network_summary,
    calculate_tag_coverage,
    classify_tag,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "unknown"),
        ("", "unknown"),
        ("no", "explicit_absent"),
        (False, "explicit_absent"),
        ("lane", "present"),
        (True, "present"),
        (["no", "lane"], "present"),
    ],
)
def test_classify_tag_distinguishes_unknown_absent_and_present(
    value: object,
    expected: str,
) -> None:
    assert classify_tag(value) == expected


def test_coverage_is_weighted_by_length_and_preserves_unknown() -> None:
    edges = gpd.GeoDataFrame(
        {"length": [100.0, 200.0, 300.0], "cycleway": ["lane", "no", None]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(0, 0), (200, 0)]),
            LineString([(0, 0), (300, 0)]),
        ],
        crs="EPSG:3857",
    )

    row = calculate_tag_coverage(edges, ["cycleway"]).iloc[0]

    assert row.to_dict() == {
        "tag": "cycleway",
        "total_length_m": 600.0,
        "recorded_length_m": 300.0,
        "present_length_m": 100.0,
        "explicit_absent_length_m": 200.0,
        "unknown_length_m": 300.0,
        "recorded_pct": 50.0,
        "unknown_pct": 50.0,
    }


def test_summary_reports_counts_and_total_length() -> None:
    edges = gpd.GeoDataFrame(
        {"length": [100.0, 250.0]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(0, 0), (250, 0)]),
        ],
        crs="EPSG:3857",
    )

    assert build_network_summary(3, 2, edges) == {
        "node_count": 3,
        "edge_count": 2,
        "total_edge_length_m": 350.0,
        "total_edge_length_km": 0.35,
    }


def test_summary_can_report_unique_street_length() -> None:
    edges = gpd.GeoDataFrame(
        {"length": [100.0, 100.0]},
        geometry=[
            LineString([(0, 0), (100, 0)]),
            LineString([(100, 0), (0, 0)]),
        ],
        crs="EPSG:3857",
    )

    summary = build_network_summary(
        2,
        2,
        edges,
        street_length_m=100.0,
    )

    assert summary["total_edge_length_m"] == 200.0
    assert summary["street_length_m"] == 100.0
    assert summary["street_length_km"] == 0.1
