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
CYCLEWAY_TAGS = ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")

ROUTE_PROFILES: dict[str, dict[str, Any]] = {
    "shortest": {
        "id": "shortest",
        "label": "距離最短",
        "description": "道路延長だけを使う比較基準",
        "color": "#2563eb",
        "enforce_prohibited": False,
        "weights": {"road_type": 0.0, "cycleway": 0.0, "unknown": 0.0},
    },
    "rule": {
        "id": "rule",
        "label": "ルール遵守優先",
        "description": "明示的な通行禁止を除外し、情報不足区間を抑える暫定モデル",
        "color": "#ea580c",
        "enforce_prohibited": True,
        "weights": {"road_type": 0.1, "cycleway": 0.1, "unknown": 0.35},
    },
    "safety": {
        "id": "safety",
        "label": "安全性優先",
        "description": "幹線道路と自転車設備のない区間を強く避ける暫定モデル",
        "color": "#15803d",
        "enforce_prohibited": True,
        "weights": {"road_type": 0.8, "cycleway": 0.6, "unknown": 0.1},
    },
    "information": {
        "id": "information",
        "label": "情報信頼性優先",
        "description": "評価に必要なOSM属性が記録された区間を優先する暫定モデル",
        "color": "#7e22ce",
        "enforce_prohibited": True,
        "weights": {"road_type": 0.0, "cycleway": 0.0, "unknown": 1.0},
    },
    "balanced": {
        "id": "balanced",
        "label": "バランス型",
        "description": "距離・道路種別・自転車設備・情報不足を組み合わせる暫定モデル",
        "color": "#dc2626",
        "enforce_prohibited": True,
        "weights": {"road_type": 0.4, "cycleway": 0.2, "unknown": 0.5},
    },
}
ROUTE_PROFILE_IDS = tuple(ROUTE_PROFILES)


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
    road_type_risk = max(
        (
            MAJOR_ROAD_RISKS.get(value.lower(), 0.0)
            for value in _tag_values(edge.get("highway"))
        ),
        default=0.0,
    )
    cycleway_risk = 0.0 if _has_cycleway_facility(edge) else 1.0
    unknown_count = sum(
        (
            _is_unknown(edge.get("bicycle")),
            not _has_cycleway_information(edge),
            _is_unknown(edge.get("maxspeed")),
            _is_unknown(edge.get("width")),
            _is_unknown(edge.get("surface")),
        )
    )
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


def calculate_profile_cost(edge: dict[str, Any], profile_id: str) -> float:
    """Return a provisional profile cost used by the Phase 4 comparison."""
    try:
        profile = ROUTE_PROFILES[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown route profile: {profile_id}") from exc

    components = calculate_edge_cost_components(edge)
    if profile["enforce_prohibited"] and components["prohibited"]:
        return math.inf

    weights = profile["weights"]
    multiplier = (
        1.0
        + weights["road_type"] * components["road_type_risk"]
        + weights["cycleway"] * components["cycleway_risk"]
        + weights["unknown"] * components["unknown_risk"]
    )
    return round(components["distance_m"] * multiplier, 6)


def build_route_result(
    graph: nx.MultiDiGraph,
    *,
    source: Hashable,
    target: Hashable,
    profile_id: str = "shortest",
) -> dict[str, Any]:
    profile = ROUTE_PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"unknown route profile: {profile_id}")

    node_path = nx.shortest_path(
        graph,
        source,
        target,
        weight=_profile_weight_function(profile_id),
    )
    selected_edges = [
        _select_profile_parallel_edge(graph, start, end, profile_id)
        for start, end in zip(node_path, node_path[1:])
    ]
    total_length = sum(edge[3]["length"] for edge in selected_edges)
    major_length = sum(
        edge[3]["length"]
        for edge in selected_edges
        if calculate_edge_cost_components(edge[3])["road_type_risk"] > 0
    )
    cycleway_length = sum(
        edge[3]["length"]
        for edge in selected_edges
        if _has_cycleway_facility(edge[3])
    )
    provisional_costs = [
        calculate_edge_cost_components(edge[3])["provisional_cost"]
        for edge in selected_edges
    ]
    profile_costs = [
        calculate_profile_cost(edge[3], profile_id) for edge in selected_edges
    ]

    summary: dict[str, Any] = {
        "profile_id": profile_id,
        "profile_label": profile["label"],
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
        "unknown_attribute_pct": _unknown_attribute_percentage(
            selected_edges, total_length
        ),
        "provisional_cost": (
            None
            if any(math.isinf(value) for value in provisional_costs)
            else round(sum(provisional_costs), 2)
        ),
        "profile_cost": (
            None
            if any(math.isinf(value) for value in profile_costs)
            else round(sum(profile_costs), 2)
        ),
    }

    return {
        "node_path": list(node_path),
        "summary": summary,
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                _edge_feature(graph, start, end, key, data, profile_id)
                for start, end, key, data in selected_edges
            ],
        },
    }


def build_route_comparison(
    graph: nx.MultiDiGraph,
    *,
    source: Hashable,
    target: Hashable,
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for profile_id in ROUTE_PROFILE_IDS:
        profile = _public_profile(ROUTE_PROFILES[profile_id])
        try:
            result = build_route_result(
                graph,
                source=source,
                target=target,
                profile_id=profile_id,
            )
        except nx.NetworkXNoPath:
            if profile_id == "shortest":
                raise
            routes.append(
                {
                    "profile": profile,
                    "available": False,
                    "error": "このプロファイルでは経路が見つかりません",
                }
            )
            continue

        routes.append(
            {
                "profile": profile,
                "available": True,
                "route": result["geojson"],
                "summary": result["summary"],
            }
        )
    return routes


def _profile_weight_function(profile_id: str):
    def weight(
        _start: Hashable,
        _end: Hashable,
        parallel_edges: dict[Hashable, dict[str, Any]],
    ) -> float | None:
        costs = [
            calculate_profile_cost(edge, profile_id)
            for edge in parallel_edges.values()
        ]
        finite_costs = [cost for cost in costs if math.isfinite(cost)]
        return min(finite_costs) if finite_costs else None

    return weight


def _select_profile_parallel_edge(
    graph: nx.MultiDiGraph,
    start: Hashable,
    end: Hashable,
    profile_id: str,
) -> tuple[Hashable, Hashable, Hashable, dict[str, Any]]:
    edges = graph.get_edge_data(start, end)
    if not edges:
        raise nx.NetworkXNoPath(f"edge {start!r} -> {end!r} is missing")
    candidates = [
        (key, data, calculate_profile_cost(data, profile_id))
        for key, data in edges.items()
    ]
    finite_candidates = [item for item in candidates if math.isfinite(item[2])]
    if not finite_candidates:
        raise nx.NetworkXNoPath(f"edge {start!r} -> {end!r} is unavailable")
    key, data, _cost = min(finite_candidates, key=lambda item: item[2])
    normalized = dict(data)
    normalized["length"] = float(normalized.get("length", 0.0))
    return start, end, key, normalized


def _edge_feature(
    graph: nx.MultiDiGraph,
    start: Hashable,
    end: Hashable,
    key: Hashable,
    data: dict[str, Any],
    profile_id: str,
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
        "cycleway:left": _json_safe(data.get("cycleway:left")),
        "cycleway:right": _json_safe(data.get("cycleway:right")),
        "cycleway:both": _json_safe(data.get("cycleway:both")),
        "maxspeed": _json_safe(data.get("maxspeed")),
        "width": _json_safe(data.get("width")),
        "surface": _json_safe(data.get("surface")),
        "cost_components": components,
        "profile_cost": round(calculate_profile_cost(data, profile_id), 2),
    }
    if math.isinf(components["provisional_cost"]):
        properties["cost_components"]["provisional_cost"] = None

    return {
        "type": "Feature",
        "geometry": mapping(geometry),
        "properties": properties,
    }


def _public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": profile["id"],
        "label": profile["label"],
        "description": profile["description"],
        "color": profile["color"],
        "weights": dict(profile["weights"]),
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


def _unknown_attribute_percentage(
    selected_edges: list[tuple[Hashable, Hashable, Hashable, dict[str, Any]]],
    total_length: float,
) -> float:
    if total_length <= 0:
        return 0.0
    weighted_unknown = sum(
        edge[3]["length"]
        * calculate_edge_cost_components(edge[3])["unknown_risk"]
        for edge in selected_edges
    )
    return round(weighted_unknown / total_length * 100, 2)


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
    if _is_unknown(value):
        return False
    values = _tag_values(value)
    return any(item.lower() not in {"", "no", "none"} for item in values)


def _has_cycleway_facility(edge: dict[str, Any]) -> bool:
    return any(_has_positive_value(edge.get(tag)) for tag in CYCLEWAY_TAGS)


def _has_cycleway_information(edge: dict[str, Any]) -> bool:
    return any(not _is_unknown(edge.get(tag)) for tag in CYCLEWAY_TAGS)


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
