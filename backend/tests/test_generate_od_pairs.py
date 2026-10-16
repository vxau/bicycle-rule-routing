from collections import Counter
from pathlib import Path

import networkx as nx
import pytest

from backend.app.evaluation import load_od_pairs
from backend.scripts.generate_od_pairs import select_od_pairs, write_od_pairs


def build_grid_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for row in range(7):
        for column in range(7):
            node = row * 7 + column
            graph.add_node(node, x=139.0 + column * 0.01, y=35.0 + row * 0.01)
            if column > 0:
                west = node - 1
                graph.add_edge(west, node, length=900)
                graph.add_edge(node, west, length=900)
            if row > 0:
                north = node - 7
                graph.add_edge(north, node, length=1100)
                graph.add_edge(node, north, length=1100)
    return graph


def test_select_od_pairs_is_reproducible_and_balanced() -> None:
    graph = build_grid_graph()

    first = select_od_pairs(graph, seed=20260914)
    second = select_od_pairs(graph, seed=20260914)

    assert first == second
    assert len(first) == 20
    assert Counter(pair.distance_band for pair in first) == {
        "short": 5, "medium": 10, "long": 5
    }
    assert [pair.od_id for pair in first] == [f"OD-{i:02d}" for i in range(1, 21)]
    assert len({
        (pair.origin_lat, pair.origin_lon, pair.destination_lat, pair.destination_lon)
        for pair in first
    }) == 20
    assert len({
        (round(pair.destination_lon - pair.origin_lon, 3) > 0,
         round(pair.destination_lat - pair.origin_lat, 3) > 0)
        for pair in first
    }) >= 3


def test_select_od_pairs_rejects_network_without_enough_pairs() -> None:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.0, y=35.0)
    graph.add_node(2, x=139.001, y=35.0)
    graph.add_edge(1, 2, length=100)
    graph.add_edge(2, 1, length=100)

    with pytest.raises(ValueError, match="20組"):
        select_od_pairs(graph)


def test_write_od_pairs_is_excel_compatible_and_readable(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "od_pairs.csv"
    pairs = select_od_pairs(build_grid_graph())

    write_od_pairs(pairs, path)

    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert load_od_pairs(path) == pairs
