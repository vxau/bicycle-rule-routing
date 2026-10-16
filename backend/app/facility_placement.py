"""Screen existing-road improvements with a fixed-route knapsack model."""

from __future__ import annotations

import math
from collections.abc import Hashable, Sequence
from dataclasses import dataclass

import networkx as nx

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
                benefit_m=round(float(record["benefit_m"]), 2),
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
