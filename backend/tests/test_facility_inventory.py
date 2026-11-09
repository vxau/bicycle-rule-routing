from copy import deepcopy

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, get_graph


def inventory_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    for node in range(6):
        graph.add_node(node, x=139 + node * .001, y=35)
    graph.add_edge(0, 1, length=100, cycleway="no", name="確認する道路")
    graph.add_edge(1, 0, length=101, cycleway="no")
    graph.add_edge(1, 2, length=200, **{"cycleway:left": "lane", "cycleway:right": "no"})
    graph.add_edge(2, 3, length=300)
    graph.add_edge(3, 4, length=400, cycleway="no")
    graph.add_edge(4, 3, length=400, cycleway="lane")
    graph.add_edge(4, 5, length=50, cycleway='["no", "none"]')
    return graph


@pytest.fixture
def inventory_client():
    graph = inventory_graph()
    app.dependency_overrides[get_graph] = lambda: graph
    try:
        yield TestClient(app), graph
    finally:
        app.dependency_overrides.clear()


def test_inventory_groups_directions_and_keeps_unknown_distinct(inventory_client):
    client, graph = inventory_client
    before = deepcopy(dict(((u, v, k), d) for u, v, k, d in graph.edges(keys=True, data=True)))
    response = client.get("/api/facilities")
    assert response.status_code == 200
    body = response.json()
    features = {f["properties"]["segment_id"]: f for f in body["features"]}
    assert body["type"] == "FeatureCollection"
    assert len(features) == 5
    assert features["0|1|0"]["properties"]["facility_state"] == "explicit_absent"
    assert features["0|1|0"]["properties"]["length_m"] == 101
    assert len(features["0|1|0"]["properties"]["directions"]) == 2
    assert features["1|2|0"]["properties"]["facility_state"] == "present"
    assert features["2|3|0"]["properties"]["facility_state"] == "unknown"
    assert features["3|4|0"]["properties"]["facility_state"] == "unknown"
    assert features["3|4|0"]["properties"]["direction_conflict"] is True
    assert features["4|5|0"]["properties"]["facility_state"] == "explicit_absent"
    assert features["0|1|0"]["geometry"]["coordinates"][0] == [139, 35]
    assert body["summary"] == {
        "segment_count": 5, "total_length_m": 1051.0,
        "states": {
            "present": {"segment_count": 1, "length_m": 200.0},
            "explicit_absent": {"segment_count": 2, "length_m": 151.0},
            "unknown": {"segment_count": 2, "length_m": 700.0},
        },
    }
    assert dict(((u, v, k), d) for u, v, k, d in graph.edges(keys=True, data=True)) == before


def test_inventory_identity_changes_when_road_data_changes(inventory_client):
    client, graph = inventory_client
    first = client.get("/api/facilities")
    assert first.status_code == 200
    first_id = first.json()["dataset_id"]
    assert client.get("/api/facilities").json()["dataset_id"] == first_id
    graph[2][3][0]["cycleway"] = "no"
    assert client.get("/api/facilities").json()["dataset_id"] != first_id


def test_empty_inventory_is_valid(inventory_client):
    client, graph = inventory_client
    graph.clear()
    response = client.get("/api/facilities")
    assert response.status_code == 200
    body = response.json()
    assert body["features"] == []
    assert body["summary"]["total_length_m"] == 0
    assert body["summary"]["segment_count"] == 0


def test_inventory_reports_missing_road_data(monkeypatch, tmp_path):
    from backend.app import main
    monkeypatch.setattr(main, "GRAPHML_PATH", tmp_path / "missing.graphml")
    get_graph.cache_clear()
    try:
        response = TestClient(app).get("/api/facilities")
        assert response.status_code == 503
        assert "道路グラフ" in response.json()["detail"]
    finally:
        get_graph.cache_clear()
