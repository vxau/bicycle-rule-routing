import networkx as nx
import osmnx as ox
import pandas as pd
from pathlib import Path

from backend.app.evaluation import ODPair
from backend.app.facility_placement import (
    FacilityCandidate,
    candidate_geojson,
    evaluate_placement,
    score_candidates,
    select_candidates,
)
from backend.scripts.generate_od_pairs import write_od_pairs
from backend.scripts.optimize_facilities import run_placement


def build_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for node in range(4):
        graph.add_node(node, x=139.0 + node * 0.001, y=35.0)
    for start, end, tag in (
        (0, 1, "no"),
        (1, 2, "no"),
        (2, 3, None),
    ):
        for u, v in ((start, end), (end, start)):
            attrs = {"length": 100.0, "highway": "residential"}
            if tag is not None:
                attrs["cycleway"] = tag
            graph.add_edge(u, v, key=0, **attrs)
    return graph


def pair(od_id: str, source: int, target: int) -> ODPair:
    return ODPair(
        od_id, "出発", 35.0, 139.0 + source * 0.001,
        "到着", 35.0, 139.0 + target * 0.001, "short"
    )


def test_candidates_count_shared_travel_and_exclude_unknown_tags() -> None:
    candidates, statistics = score_candidates(
        build_graph(), [pair("A", 0, 2), pair("B", 0, 1)]
    )

    assert statistics["available_od_count"] == 2
    assert statistics["baseline_exposure_m"] == 300.0
    assert len(candidates) == 2
    assert [(candidate.segment_id, candidate.od_count, candidate.benefit_m)
            for candidate in candidates] == [
        ("0|1|0", 2, 200.0),
        ("1|2|0", 1, 100.0),
    ]
    selected = select_candidates(candidates, budget_m=100)
    assert [candidate.segment_id for candidate in selected] == ["0|1|0"]


def test_optimizer_obeys_budget_and_prefers_combined_gain() -> None:
    candidates, _ = score_candidates(build_graph(), [pair("A", 0, 2)])
    assert select_candidates(candidates, budget_m=199) == [candidates[0]]
    assert select_candidates(candidates, budget_m=200) == candidates


def test_optimizer_finds_better_combination_than_gain_per_meter_greedy() -> None:
    candidates = [
        FacilityCandidate(name, 35, 139, 35, 139, length, 1, gain)
        for name, length, gain in (
            ("a", 60, 100), ("b", 50, 80), ("c", 50, 80)
        )
    ]

    assert [candidate.segment_id for candidate in select_candidates(
        candidates, budget_m=100
    )] == ["b", "c"]


def test_recalculation_reduces_explicit_absence_without_mutating_source() -> None:
    graph = build_graph()

    candidates, selected, summary, comparisons = evaluate_placement(
        graph, [pair("A", 0, 2), pair("B", 0, 1)], budget_m=100
    )

    assert [candidate.segment_id for candidate in selected] == ["0|1|0"]
    assert summary["before_exposure_m"] == 300.0
    assert summary["after_exposure_m"] == 100.0
    assert summary["rerouted_reduction_m"] == 200.0
    assert summary["route_changed_od_count"] == 0
    assert summary["before_total_distance_m"] == 300.0
    assert summary["after_total_distance_m"] == 300.0
    assert [row["after_exposure_m"] for row in comparisons] == [100.0, 0.0]
    assert graph[0][1][0]["cycleway"] == "no"

    geojson = candidate_geojson(graph, candidates, selected)
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    assert [feature["properties"]["selected"] for feature in geojson["features"]] == [
        True, False
    ]
    assert geojson["features"][0]["geometry"]["coordinates"] == (
        (139.0, 35.0), (139.001, 35.0)
    )


def test_aggregate_exposure_rounds_after_summing_all_od_pairs() -> None:
    graph = build_graph()
    for start, end in ((0, 1), (1, 0)):
        graph[start][end][0]["length"] = 1.004
    pairs = [pair("A", 0, 1), pair("B", 0, 1)]

    _, _, summary, _ = evaluate_placement(graph, pairs, budget_m=0)

    assert summary["baseline_exposure_m"] == 2.01
    assert summary["before_exposure_m"] == 2.01


def test_fixed_route_benefit_matches_rerun_when_routes_do_not_change() -> None:
    graph = build_graph()
    for start, end in ((0, 1), (1, 0), (1, 2), (2, 1)):
        graph[start][end][0]["length"] = 1.004

    _, _, summary, _ = evaluate_placement(
        graph, [pair("A", 0, 2)], budget_m=4
    )

    assert summary["route_changed_od_count"] == 0
    assert summary["residual_exposure_m"] == summary["after_exposure_m"] == 0.0


def test_recalculation_can_change_another_od_route() -> None:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for node in range(3):
        graph.add_node(node, x=139.0 + node * 0.001, y=35.0)
    common = {"highway": "residential", "bicycle": "yes",
              "maxspeed": "30", "width": "4", "surface": "asphalt"}
    graph.add_edge(0, 1, key=0, length=100.0, cycleway="no", **common)
    graph.add_edge(1, 2, key=0, length=20.0, cycleway="lane", **common)
    graph.add_edge(0, 2, key=0, length=125.0, cycleway="lane", **common)

    _, selected, summary, comparisons = evaluate_placement(
        graph, [pair("A", 0, 1), pair("B", 0, 2)], budget_m=100
    )

    assert [candidate.segment_id for candidate in selected] == ["0|1|0"]
    assert summary["route_changed_od_count"] == 1
    assert comparisons[1]["before_distance_m"] == 125.0
    assert comparisons[1]["after_distance_m"] == 120.0
    assert comparisons[1]["route_changed"] is True


def test_placement_export_has_selected_segments_and_exposure(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    ox.io.save_graphml(build_graph(), filepath=graph_path)
    od_path = tmp_path / "od.csv"
    write_od_pairs([pair("A", 0, 2), pair("B", 0, 1)], od_path)
    output_path = tmp_path / "out" / "candidates.csv"
    comparison_path = tmp_path / "out" / "placement_comparison.csv"
    summary_path = tmp_path / "out" / "summary.json"

    summary = run_placement(
        graph_path=graph_path,
        od_path=od_path,
        output_path=output_path,
        comparison_path=comparison_path,
        summary_path=summary_path,
        budget_m=100,
    )

    assert summary["selected_count"] == 1
    assert summary["selected_benefit_m"] == 200.0
    assert summary["residual_exposure_m"] == 100.0
    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")
    frame = pd.read_csv(output_path, encoding="utf-8-sig")
    assert frame.loc[frame.selected, "segment_id"].tolist() == ["0|1|0"]
    assert comparison_path.read_bytes().startswith(b"\xef\xbb\xbf")
    comparison = pd.read_csv(comparison_path, encoding="utf-8-sig")
    assert comparison["after_exposure_m"].tolist() == [100.0, 0.0]
    assert summary_path.exists()
