import networkx as nx
import osmnx as ox
import pandas as pd
from pathlib import Path

from backend.app.evaluation import ODPair
from backend.app.facility_placement import FacilityCandidate, score_candidates, select_candidates
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


def test_placement_export_has_selected_segments_and_exposure(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.graphml"
    ox.io.save_graphml(build_graph(), filepath=graph_path)
    od_path = tmp_path / "od.csv"
    write_od_pairs([pair("A", 0, 2), pair("B", 0, 1)], od_path)
    output_path = tmp_path / "out" / "candidates.csv"
    summary_path = tmp_path / "out" / "summary.json"

    summary = run_placement(
        graph_path=graph_path,
        od_path=od_path,
        output_path=output_path,
        summary_path=summary_path,
        budget_m=100,
    )

    assert summary["selected_count"] == 1
    assert summary["selected_benefit_m"] == 200.0
    assert summary["residual_exposure_m"] == 100.0
    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")
    frame = pd.read_csv(output_path, encoding="utf-8-sig")
    assert frame.loc[frame.selected, "segment_id"].tolist() == ["0|1|0"]
    assert summary_path.exists()
