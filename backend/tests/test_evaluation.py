from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from backend.app.evaluation import (
    ODPair,
    evaluate_profiles,
    load_od_pairs,
    route_signature,
)
from backend.app.routing import ROUTE_PROFILE_IDS


def valid_row() -> dict[str, object]:
    return {
        "od_id": "OD-01",
        "origin_label": "地点01-A",
        "origin_lat": 35.0,
        "origin_lon": 139.0,
        "destination_label": "地点01-B",
        "destination_lat": 35.001,
        "destination_lon": 139.001,
        "distance_band": "short",
    }


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_load_od_pairs_reads_valid_csv(tmp_path: Path) -> None:
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [valid_row()])

    pairs = load_od_pairs(path)

    assert pairs[0].od_id == "OD-01"
    assert pairs[0].origin_lat == 35.0


def test_load_od_pairs_rejects_missing_column(tmp_path: Path) -> None:
    row = valid_row()
    del row["destination_lon"]
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [row])

    with pytest.raises(ValueError, match="必須列"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_duplicate_id(tmp_path: Path) -> None:
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [valid_row(), valid_row()])

    with pytest.raises(ValueError, match="重複"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_out_of_range_latitude(tmp_path: Path) -> None:
    row = valid_row()
    row["origin_lat"] = 91
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [row])

    with pytest.raises(ValueError, match="緯度"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "od_pairs.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="空"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_non_numeric_coordinate(tmp_path: Path) -> None:
    row = valid_row()
    row["destination_lon"] = "east"
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [row])

    with pytest.raises(ValueError, match="数値"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_out_of_range_longitude(tmp_path: Path) -> None:
    row = valid_row()
    row["origin_lon"] = -181
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [row])

    with pytest.raises(ValueError, match="経度"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_blank_id(tmp_path: Path) -> None:
    row = valid_row()
    row["od_id"] = "   "
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [row])

    with pytest.raises(ValueError, match="空欄"):
        load_od_pairs(path)


def test_load_od_pairs_rejects_unknown_distance_band(tmp_path: Path) -> None:
    row = valid_row()
    row["distance_band"] = "extra-long"
    path = tmp_path / "od_pairs.csv"
    write_rows(path, [row])

    with pytest.raises(ValueError, match="distance_band"):
        load_od_pairs(path)


def test_route_signature_uses_order_and_parallel_edge_key() -> None:
    first = route_signature([(1, 2, 0), (2, 3, 0)])
    same = route_signature([(1, 2, 0), (2, 3, 0)])
    other_key = route_signature([(1, 2, 1), (2, 3, 0)])
    reversed_order = route_signature([(2, 3, 0), (1, 2, 0)])

    assert first == same
    assert len(first) == 64
    assert first != other_key
    assert first != reversed_order


def build_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.000, y=35.000)
    graph.add_node(2, x=139.001, y=35.000)
    graph.add_node(3, x=139.001, y=35.001)
    graph.add_node(4, x=139.002, y=35.000)
    for start, end in ((1, 2), (2, 4)):
        graph.add_edge(start, end, key=0, length=100.0, highway="primary")
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


def build_pair(
    *,
    od_id: str = "OD-01",
    destination_lat: float = 35.0,
    destination_lon: float = 139.002,
) -> ODPair:
    return ODPair(
        od_id=od_id,
        origin_label=f"{od_id}-A",
        origin_lat=35.0,
        origin_lon=139.0,
        destination_label=f"{od_id}-B",
        destination_lat=destination_lat,
        destination_lon=destination_lon,
        distance_band="short",
    )


def test_evaluate_profiles_returns_five_rows_for_each_od() -> None:
    pairs = [
        build_pair(),
        build_pair(
            od_id="OD-02",
            destination_lat=35.001,
            destination_lon=139.001,
        ),
    ]

    result = evaluate_profiles(build_graph(), pairs)

    assert len(result) == 10
    assert set(result["profile_id"]) == set(ROUTE_PROFILE_IDS)
    shortest = result.query(
        "od_id == 'OD-01' and profile_id == 'shortest'"
    ).iloc[0]
    assert shortest["distance_increase_pct"] == 0.0
    assert bool(shortest["same_as_shortest"]) is True
    assert result.groupby("od_id")["unique_route_count"].nunique().eq(1).all()
    assert result["same_route_profile_pct"].between(0, 100).all()


def test_evaluate_profiles_preserves_unavailable_rows() -> None:
    graph = build_graph()
    graph.add_node(9, x=140.0, y=36.0)
    disconnected = ODPair(
        od_id="OD-99",
        origin_label="接続なし-A",
        origin_lat=36.0,
        origin_lon=140.0,
        destination_label="接続なし-B",
        destination_lat=35.0,
        destination_lon=139.002,
        distance_band="long",
    )

    result = evaluate_profiles(graph, [build_pair(), disconnected])

    assert len(result) == 10
    assert result.query("od_id == 'OD-01'")["available"].all()
    unavailable = result.query("od_id == 'OD-99'")
    assert len(unavailable) == 5
    assert not unavailable["available"].any()
    assert unavailable["error"].notna().all()
