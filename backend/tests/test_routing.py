import math

import networkx as nx
from shapely.geometry import LineString

from backend.app.routing import (
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
        "provisional_cost": 420.0,
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
