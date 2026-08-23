from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Hashable

import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, mapping


MAJOR_ROAD_RISKS = {
    "trunk": 1.0,
    "primary": 1.0,
    "secondary": 0.5,
    "tertiary": 0.25,
}

# These weights are provisional and are not used to choose the shortest route.
PROVISIONAL_WEIGHTS = {
    "road_type": 0.4,
    "cycleway": 0.2,
    "unknown": 0.5,
}

UNKNOWN_TAGS = ("bicycle", "cycleway", "maxspeed", "width", "surface")


def load_graph(path: Path) -> nx.MultiDiGraph:
    if not path.exists():
        raise FileNotFoundError(path)
    return ox.io.load_graphml(path)


def find_nearest_node(
    graph: nx.MultiDiGraph,
    *,
    latitude: float,
    longitude: float,
) -> Hashable:
    """Find a nearby graph node without requiring optional spatial packages."""
    latitude_scale = math.cos(math.radians(latitude))

    def squared_distance(node: Hashable) -> float:
        data = graph.nodes[node]
        delta_lon = (float(data["x"]) - longitude) * latitude_scale
        delta_lat = float(data["y"]) - latitude
        return delta_lon * delta_lon + delta_lat * delta_lat

    return min(graph.nodes, key=squared_distance)


def calculate_edge_cost_components(edge: dict[str, Any]) -> dict[str, Any]:
    """Calculate provisional components without claiming validated risk values."""
    distance_m = float(edge.get("length", 0.0))
    highway = _first_tag_value(edge.get("highway"))
    road_type_risk = MAJOR_ROAD_RISKS.get(highway, 0.0)
    cycleway_risk = 0.0 if _has_positive_value(edge.get("cycleway")) else 1.0
    unknown_count = sum(_is_unknown(edge.get(tag)) for tag in UNKNOWN_TAGS)
    unknown_risk = round(unknown_count / len(UNKNOWN_TAGS), 2)
    prohibited = _has_no_value(edge.get("bicycle")) or _has_no_value(
        edge.get("access")
    )

    if prohibited:
        provisional_cost = math.inf
    else:
        multiplier = (
            1.0
            + PROVISIONAL_WEIGHTS["road_type"] * road_type_risk
            + PROVISIONAL_WEIGHTS["cycleway"] * cycleway_risk
            + PROVISIONAL_WEIGHTS["unknown"] * unknown_risk
        )
        provisional_cost = round(distance_m * multiplier, 2)

    return {
        "distance_m": distance_m,
        "prohibited": prohibited,
        "road_type_risk": road_type_risk,
        "cycleway_risk": cycleway_risk,
        "unknown_risk": unknown_risk,
        "provisional_cost": provisional_cost,
    }


def build_route_result(
    graph: nx.MultiDiGraph,
    *,
    source: Hashable,
    target: Hashable,
) -> dict[str, Any]:
    node_path = nx.shortest_path(graph, source, target, weight="length")
    selected_edges = [
        _select_shortest_parallel_edge(graph, start, end)
        for start, end in zip(node_path, node_path[1:])
    ]
    total_length = sum(edge[3]["length"] for edge in selected_edges)
    major_length = sum(
        edge[3]["length"]
        for edge in selected_edges
        if MAJOR_ROAD_RISKS.get(_first_tag_value(edge[3].get("highway")), 0.0)
        > 0
    )
    cycleway_length = sum(
        edge[3]["length"]
        for edge in selected_edges
        if _has_positive_value(edge[3].get("cycleway"))
    )
    provisional_costs = [
        calculate_edge_cost_components(edge[3])["provisional_cost"]
        for edge in selected_edges
    ]

    summary: dict[str, Any] = {
        "distance_m": round(total_length, 2),
        "edge_count": len(selected_edges),
        "major_road_distance_m": round(major_length, 2),
        "major_road_pct": _length_percentage(major_length, total_length),
        "cycleway_distance_m": round(cycleway_length, 2),
        "cycleway_pct": _length_percentage(cycleway_length, total_length),
        "traffic_signal_count": _count_traffic_signals(graph, node_path),
        "unknown_maxspeed_pct": _unknown_length_percentage(
            selected_edges, "maxspeed", total_length
        ),
        "unknown_width_pct": _unknown_length_percentage(
            selected_edges, "width", total_length
        ),
        "unknown_surface_pct": _unknown_length_percentage(
            selected_edges, "surface", total_length
        ),
        "provisional_cost": (
            None
            if any(math.isinf(value) for value in provisional_costs)
            else round(sum(provisional_costs), 2)
        ),
    }

    return {
        "node_path": list(node_path),
        "summary": summary,
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                _edge_feature(graph, start, end, key, data)
                for start, end, key, data in selected_edges
            ],
        },
    }


def _select_shortest_parallel_edge(
    graph: nx.MultiDiGraph,
    start: Hashable,
    end: Hashable,
) -> tuple[Hashable, Hashable, Hashable, dict[str, Any]]:
    edges = graph.get_edge_data(start, end)
    if not edges:
        raise nx.NetworkXNoPath(f"edge {start!r} -> {end!r} is missing")
    key, data = min(
        edges.items(),
        key=lambda item: float(item[1].get("length", math.inf)),
    )
    normalized = dict(data)
    normalized["length"] = float(normalized.get("length", 0.0))
    return start, end, key, normalized


def _edge_feature(
    graph: nx.MultiDiGraph,
    start: Hashable,
    end: Hashable,
    key: Hashable,
    data: dict[str, Any],
) -> dict[str, Any]:
    geometry = data.get("geometry") or LineString(
        [
            (float(graph.nodes[start]["x"]), float(graph.nodes[start]["y"])),
            (float(graph.nodes[end]["x"]), float(graph.nodes[end]["y"])),
        ]
    )
    components = calculate_edge_cost_components(data)
    properties = {
        "u": start,
        "v": end,
        "key": key,
        "length_m": data["length"],
        "highway": _json_safe(data.get("highway")),
        "cycleway": _json_safe(data.get("cycleway")),
        "maxspeed": _json_safe(data.get("maxspeed")),
        "width": _json_safe(data.get("width")),
        "surface": _json_safe(data.get("surface")),
        "cost_components": components,
    }
    if math.isinf(components["provisional_cost"]):
        properties["cost_components"]["provisional_cost"] = None

    return {
        "type": "Feature",
        "geometry": mapping(geometry),
        "properties": properties,
    }


def _count_traffic_signals(
    graph: nx.MultiDiGraph,
    node_path: list[Hashable],
) -> int:
    return sum(
        _contains_value(graph.nodes[node].get("highway"), "traffic_signals")
        for node in node_path
    )


def _unknown_length_percentage(
    selected_edges: list[tuple[Hashable, Hashable, Hashable, dict[str, Any]]],
    tag: str,
    total_length: float,
) -> float:
    unknown_length = sum(
        edge[3]["length"] for edge in selected_edges if _is_unknown(edge[3].get(tag))
    )
    return _length_percentage(unknown_length, total_length)


def _length_percentage(part: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round(part / total * 100, 2)


def _is_unknown(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _has_no_value(value: object) -> bool:
    values = _tag_values(value)
    return any(item.lower() in {"no", "private"} for item in values)


def _has_positive_value(value: object) -> bool:
    values = _tag_values(value)
    return any(item.lower() not in {"", "no", "none"} for item in values)


def _contains_value(value: object, expected: str) -> bool:
    return expected in _tag_values(value)


def _first_tag_value(value: object) -> str:
    values = _tag_values(value)
    return values[0].lower() if values else ""


def _tag_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass
    return [str(value)]


def _json_safe(value: object) -> object:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value
