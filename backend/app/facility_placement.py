"""Screen existing-road improvements with a fixed-route knapsack model."""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import asdict, dataclass

import networkx as nx
from shapely.geometry import LineString, mapping

from backend.app.evaluation import ODPair
from backend.app.osm_analysis import classify_tag
from backend.app.routing import (
    CYCLEWAY_TAGS,
    _tag_values,
    build_route_result,
    find_nearest_node,
)


@dataclass(frozen=True)
class FacilityCandidate:
    segment_id: str
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    length_m: float
    od_count: int
    benefit_m: float


def _segment_key(u: Hashable, v: Hashable, key: Hashable) -> tuple[str, str, str]:
    start, end = sorted((str(u), str(v)))
    return start, end, str(key)


def _facility_state(data: dict[str, object]) -> str:
    states = [classify_tag(_tag_values(data.get(tag))) for tag in CYCLEWAY_TAGS]
    if "present" in states:
        return "present"
    if "explicit_absent" in states:
        return "explicit_absent"
    return "unknown"


def score_candidates(
    graph: nx.MultiDiGraph,
    od_pairs: Sequence[ODPair],
    *,
    profile_id: str = "balanced",
) -> tuple[list[FacilityCandidate], dict[str, float | int]]:
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for u, v, key, data in graph.edges(keys=True, data=True):
        groups.setdefault(_segment_key(u, v, key), []).append(data)

    used: dict[tuple[str, str, str], dict[str, object]] = {}
    baseline_exposure = 0.0
    available_count = 0
    for pair in od_pairs:
        source = find_nearest_node(
            graph, latitude=pair.origin_lat, longitude=pair.origin_lon
        )
        target = find_nearest_node(
            graph, latitude=pair.destination_lat, longitude=pair.destination_lon
        )
        try:
            route = build_route_result(
                graph, source=source, target=target, profile_id=profile_id
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        available_count += 1
        for u, v, key in route["edge_path"]:
            data = graph[u][v][key]
            if _facility_state(data) != "explicit_absent":
                continue
            length = float(data["length"])
            baseline_exposure += length
            group_key = _segment_key(u, v, key)
            if not all(
                _facility_state(member) == "explicit_absent"
                for member in groups[group_key]
            ):
                continue
            record = used.setdefault(
                group_key,
                {"u": u, "v": v, "od_ids": set(), "benefit_m": 0.0},
            )
            record["od_ids"].add(pair.od_id)
            record["benefit_m"] += length

    candidates = []
    for key, record in sorted(used.items()):
        u, v = record["u"], record["v"]
        candidates.append(
            FacilityCandidate(
                segment_id="|".join(key),
                start_lat=float(graph.nodes[u]["y"]),
                start_lon=float(graph.nodes[u]["x"]),
                end_lat=float(graph.nodes[v]["y"]),
                end_lon=float(graph.nodes[v]["x"]),
                length_m=max(float(data["length"]) for data in groups[key]),
                od_count=len(record["od_ids"]),
                benefit_m=float(record["benefit_m"]),
            )
        )
    return candidates, {
        "evaluated_od_count": len(od_pairs),
        "available_od_count": available_count,
        "baseline_exposure_m": round(baseline_exposure, 2),
        "candidate_count": len(candidates),
    }


def select_candidates(
    candidates: Sequence[FacilityCandidate], *, budget_m: float
) -> list[FacilityCandidate]:
    if not 0 <= budget_m <= 20_000:
        raise ValueError("整備延長上限は0〜20,000 mで指定してください")
    capacity = math.floor(budget_m)
    scores = [-math.inf] * (capacity + 1)
    choices: list[tuple[int, ...]] = [()] * (capacity + 1)
    scores[0] = 0.0
    for index, candidate in enumerate(candidates):
        if candidate.length_m <= 0:
            raise ValueError("候補道路の長さは正の値が必要です")
        cost = math.ceil(candidate.length_m)
        for used in range(capacity, cost - 1, -1):
            previous = scores[used - cost]
            new_score = previous + candidate.benefit_m
            if new_score > scores[used]:
                scores[used] = new_score
                choices[used] = choices[used - cost] + (index,)
    best_capacity = max(range(capacity + 1), key=lambda used: scores[used])
    selected = [candidates[index] for index in choices[best_capacity]]
    assert sum(candidate.length_m for candidate in selected) <= budget_m + 1e-9
    return selected


def _improved_graph(
    graph: nx.MultiDiGraph, selected: Sequence[FacilityCandidate]
) -> nx.MultiDiGraph:
    improved = graph.copy()
    selected_ids = {candidate.segment_id for candidate in selected}
    for u, v, key, data in improved.edges(keys=True, data=True):
        if "|".join(_segment_key(u, v, key)) not in selected_ids:
            continue
        for tag in CYCLEWAY_TAGS:
            data.pop(tag, None)
        data["cycleway"] = "lane"
    return improved


def _route_measurements(
    graph: nx.MultiDiGraph, pair: ODPair
) -> dict[str, object]:
    source = find_nearest_node(
        graph, latitude=pair.origin_lat, longitude=pair.origin_lon
    )
    target = find_nearest_node(
        graph, latitude=pair.destination_lat, longitude=pair.destination_lon
    )
    try:
        route = build_route_result(
            graph, source=source, target=target, profile_id="balanced"
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return {"available": False, "distance_m": None, "exposure_m": None,
                "unknown_m": None, "edge_path": None}
    exposure = 0.0
    unknown = 0.0
    for u, v, key in route["edge_path"]:
        data = graph[u][v][key]
        state = _facility_state(data)
        if state == "explicit_absent":
            exposure += float(data["length"])
        elif state == "unknown":
            unknown += float(data["length"])
    return {
        "available": True,
        "distance_m": float(route["summary"]["distance_m"]),
        "exposure_m": exposure,
        "unknown_m": unknown,
        "edge_path": route["edge_path"],
    }


def evaluate_placement(
    graph: nx.MultiDiGraph,
    od_pairs: Sequence[ODPair],
    *,
    budget_m: float = 1_000.0,
) -> tuple[
    list[FacilityCandidate],
    list[FacilityCandidate],
    dict[str, float | int | str],
    list[dict[str, object]],
]:
    candidates, statistics = score_candidates(graph, od_pairs)
    selected = select_candidates(candidates, budget_m=budget_m)
    improved = _improved_graph(graph, selected)
    comparisons: list[dict[str, object]] = []
    before_distance = after_distance = 0.0
    before_exposure = after_exposure = 0.0
    before_unknown = after_unknown = 0.0
    changed_count = 0
    for pair in od_pairs:
        before = _route_measurements(graph, pair)
        after = _route_measurements(improved, pair)
        if before["available"]:
            before_distance += float(before["distance_m"])
            before_exposure += float(before["exposure_m"])
            before_unknown += float(before["unknown_m"])
        if after["available"]:
            after_distance += float(after["distance_m"])
            after_exposure += float(after["exposure_m"])
            after_unknown += float(after["unknown_m"])
        comparable = bool(before["available"] and after["available"])
        route_changed = (
            before["edge_path"] != after["edge_path"] if comparable else None
        )
        if route_changed:
            changed_count += 1
        prior_distance = float(before["distance_m"]) if comparable else 0.0
        comparisons.append(
            {
                "od_id": pair.od_id,
                "available_before": before["available"],
                "available_after": after["available"],
                "before_distance_m": before["distance_m"],
                "after_distance_m": after["distance_m"],
                "distance_change_pct": (
                    round(
                        (float(after["distance_m"]) - prior_distance)
                        / prior_distance * 100, 2
                    )
                    if comparable and prior_distance > 0
                    else None
                ),
                "before_exposure_m": (
                    round(float(before["exposure_m"]), 2)
                    if before["available"] else None
                ),
                "after_exposure_m": (
                    round(float(after["exposure_m"]), 2)
                    if after["available"] else None
                ),
                "exposure_reduction_m": (
                    round(float(before["exposure_m"]) - float(after["exposure_m"]), 2)
                    if comparable else None
                ),
                "before_unknown_m": (
                    round(float(before["unknown_m"]), 2)
                    if before["available"] else None
                ),
                "after_unknown_m": (
                    round(float(after["unknown_m"]), 2)
                    if after["available"] else None
                ),
                "route_changed": route_changed,
            }
        )
    fixed_benefit_raw = sum(item.benefit_m for item in selected)
    summary: dict[str, float | int | str] = {
        "model": "fixed_route_explicit_absence",
        "profile_id": "balanced",
        "budget_m": budget_m,
        "used_length_m": round(sum(item.length_m for item in selected), 2),
        "selected_count": len(selected),
        "selected_benefit_m": round(fixed_benefit_raw, 2),
        "residual_exposure_m": round(before_exposure - fixed_benefit_raw, 2),
        **statistics,
        "before_total_distance_m": round(before_distance, 2),
        "after_total_distance_m": round(after_distance, 2),
        "before_exposure_m": round(before_exposure, 2),
        "after_exposure_m": round(after_exposure, 2),
        "rerouted_reduction_m": round(before_exposure - after_exposure, 2),
        "before_unknown_m": round(before_unknown, 2),
        "after_unknown_m": round(after_unknown, 2),
        "route_changed_od_count": changed_count,
    }
    return candidates, selected, summary, comparisons


def candidate_geojson(
    graph: nx.MultiDiGraph,
    candidates: Sequence[FacilityCandidate],
    selected: Sequence[FacilityCandidate],
) -> dict[str, object]:
    selected_ids = {candidate.segment_id for candidate in selected}
    geometries = {}
    for u, v, key, data in graph.edges(keys=True, data=True):
        segment_id = "|".join(_segment_key(u, v, key))
        geometries.setdefault(segment_id, data.get("geometry"))
    features = []
    for candidate in candidates:
        geometry = geometries.get(candidate.segment_id) or LineString(
            [(candidate.start_lon, candidate.start_lat),
             (candidate.end_lon, candidate.end_lat)]
        )
        features.append({
            "type": "Feature",
            "geometry": mapping(geometry),
            "properties": {
                **asdict(candidate),
                "selected": candidate.segment_id in selected_ids,
            },
        })
    return {"type": "FeatureCollection", "features": features}
