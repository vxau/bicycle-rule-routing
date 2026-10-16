from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd

from backend.app.evaluation import ODPair
from backend.scripts.generate_od_pairs import write_od_pairs
from backend.scripts.evaluate_profiles import run_evaluation


def test_run_evaluation_exports_all_three_excel_compatible_csvs(tmp_path: Path) -> None:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.0, y=35.0)
    graph.add_node(2, x=139.001, y=35.0)
    graph.add_edge(1, 2, length=100.0, highway="residential", cycleway="no")
    graph.add_edge(2, 1, length=100.0, highway="residential", cycleway="no")
    graph_path = tmp_path / "graph.graphml"
    ox.io.save_graphml(graph, filepath=graph_path)
    od_path = tmp_path / "od.csv"
    write_od_pairs(
        [ODPair("OD-01", "出発", 35.0, 139.0, "到着", 35.0, 139.001, "short")],
        od_path,
    )
    outputs = [tmp_path / "results" / name for name in (
        "route_comparison.csv", "sensitivity_analysis.csv", "sensitivity_summary.csv"
    )]

    counts = run_evaluation(
        graph_path=graph_path,
        od_path=od_path,
        comparison_path=outputs[0],
        sensitivity_path=outputs[1],
        summary_path=outputs[2],
    )

    assert counts == {
        "comparison_rows": 5,
        "sensitivity_rows": 45,
        "summary_rows": 45,
    }
    for path, expected_rows in zip(outputs, (5, 45, 45)):
        assert path.read_bytes().startswith(b"\xef\xbb\xbf")
        assert len(pd.read_csv(path, encoding="utf-8-sig")) == expected_rows
