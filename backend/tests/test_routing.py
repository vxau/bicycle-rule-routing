import math

import networkx as nx
from shapely.geometry import LineString

from backend.app.routing import (
    ROUTE_PROFILE_IDS,
    build_route_comparison,
    build_route_result,
    calculate_edge_cost_components,
    find_nearest_node,
)


def build_test_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.0000, y=35.0000)
    graph.add_node(2, x=139.0010, y=35.0000, highway="traffic_signals")
    graph.add_node(3, x=139.0020, y=35.0000)
    graph.add_edge(
        1,
        2,
        key=0,
        length=100.0,
        highway="primary",
        maxspeed="50",
        geometry=LineString([(139.0000, 35.0000), (139.0010, 35.0000)]),
    )
    graph.add_edge(
        2,
        3,
        key=0,
        length=200.0,
        highway="residential",
        cycleway="lane",
        maxspeed="30",
        width="4",
        surface="asphalt",
        geometry=LineString([(139.0010, 35.0000), (139.0020, 35.0000)]),
    )
    graph.add_edge(
        1,
        3,
        key=0,
        length=400.0,
        highway="residential",
        geometry=LineString([(139.0000, 35.0000), (139.0020, 35.0000)]),
    )
    return graph


def test_find_nearest_node_uses_graph_coordinates() -> None:
    graph = build_test_graph()

    node = find_nearest_node(graph, latitude=35.00001, longitude=139.0011)

    assert node == 2


def test_shortest_route_reports_geometry_and_research_metrics() -> None:
    graph = build_test_graph()

    result = build_route_result(graph, source=1, target=3)

    assert result["node_path"] == [1, 2, 3]
    assert result["summary"] == {
        "profile_id": "shortest",
        "profile_label": "距離最短",
        "distance_m": 300.0,
        "edge_count": 2,
        "major_road_distance_m": 100.0,
        "major_road_pct": 33.33,
        "cycleway_distance_m": 200.0,
        "cycleway_pct": 66.67,
        "traffic_signal_count": 1,
        "unknown_maxspeed_pct": 0.0,
        "unknown_width_pct": 33.33,
        "unknown_surface_pct": 33.33,
        "unknown_attribute_pct": 40.0,
        "provisional_cost": 420.0,
        "profile_cost": 300.0,
    }
    assert result["geojson"]["type"] == "FeatureCollection"
    assert len(result["geojson"]["features"]) == 2


def test_edge_cost_components_separate_restrictions_and_soft_risks() -> None:
    components = calculate_edge_cost_components(
        {
            "length": 100.0,
            "highway": "primary",
            "bicycle": "no",
            "cycleway": None,
            "maxspeed": None,
            "width": None,
            "surface": "asphalt",
        }
    )

    assert components == {
        "distance_m": 100.0,
        "prohibited": True,
        "road_type_risk": 1.0,
        "cycleway_risk": 1.0,
        "unknown_risk": 0.6,
        "provisional_cost": math.inf,
    }


def test_access_no_and_private_are_explicit_prohibitions() -> None:
    for access in ("no", "private"):
        components = calculate_edge_cost_components(
            {
                "length": 100.0,
                "highway": "service",
                "access": access,
            }
        )

        assert components["prohibited"] is True
        assert components["provisional_cost"] == math.inf


def test_side_specific_cycleway_counts_as_bicycle_facility() -> None:
    edge = {
        "length": 100.0,
        "highway": "residential",
        "cycleway:left": "lane",
        "maxspeed": "30",
        "width": "4",
        "surface": "asphalt",
    }
    components = calculate_edge_cost_components(edge)

    assert components["cycleway_risk"] == 0.0

    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.0000, y=35.0000)
    graph.add_node(2, x=139.0010, y=35.0000)
    graph.add_edge(1, 2, key=0, **edge)

    result = build_route_result(graph, source=1, target=2)

    assert result["summary"]["cycleway_pct"] == 100.0


def test_nan_cycleway_value_does_not_count_as_bicycle_facility() -> None:
    components = calculate_edge_cost_components(
        {
            "length": 100.0,
            "highway": "residential",
            "cycleway": math.nan,
        }
    )

    assert components["cycleway_risk"] == 1.0


def test_multi_value_highway_uses_highest_provisional_risk() -> None:
    components = calculate_edge_cost_components(
        {
            "length": 100.0,
            "highway": ["unclassified", "tertiary"],
            "cycleway": "lane",
        }
    )

    assert components["road_type_risk"] == 0.25


def build_profile_test_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.0000, y=35.0000)
    graph.add_node(2, x=139.0010, y=35.0000)
    graph.add_node(3, x=139.0010, y=35.0010)
    graph.add_node(4, x=139.0020, y=35.0000)

    for start, end in ((1, 2), (2, 4)):
        graph.add_edge(
            start,
            end,
            key=0,
            length=100.0,
            highway="primary",
        )

    for start, end in ((1, 3), (3, 4)):
        graph.add_edge(
            start,
            end,
            key=0,
            length=130.0,
            highway="residential",
            bicycle="yes",
            cycleway="lane",
            maxspeed="30",
            width="4",
            surface="asphalt",
        )
    return graph


def test_safety_profile_can_choose_a_longer_bicycle_friendly_route() -> None:
    graph = build_profile_test_graph()

    shortest = build_route_result(graph, source=1, target=4, profile_id="shortest")
    safety = build_route_result(graph, source=1, target=4, profile_id="safety")

    assert shortest["node_path"] == [1, 2, 4]
    assert shortest["summary"]["distance_m"] == 200.0
    assert safety["node_path"] == [1, 3, 4]
    assert safety["summary"]["distance_m"] == 260.0
    assert safety["summary"]["cycleway_pct"] == 100.0


def test_rule_profile_avoids_explicit_bicycle_prohibition() -> None:
    graph = build_profile_test_graph()
    graph.edges[1, 2, 0]["bicycle"] = "no"

    shortest = build_route_result(graph, source=1, target=4, profile_id="shortest")
    rule = build_route_result(graph, source=1, target=4, profile_id="rule")

    assert shortest["node_path"] == [1, 2, 4]
    assert rule["node_path"] == [1, 3, 4]


def test_route_comparison_returns_every_phase_four_profile() -> None:
    graph = build_profile_test_graph()

    result = build_route_comparison(graph, source=1, target=4)

    assert [route["profile"]["id"] for route in result] == list(ROUTE_PROFILE_IDS)
    assert all(route["available"] for route in result)
    assert result[0]["summary"]["profile_id"] == "shortest"


def test_route_summary_uses_all_five_unknown_tags_for_aggregate_rate() -> None:
    graph = build_test_graph()

    result = build_route_result(graph, source=1, target=3)

    assert result["summary"]["unknown_attribute_pct"] == 40.0
