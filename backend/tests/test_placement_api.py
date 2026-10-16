from fastapi.testclient import TestClient

from backend.app.main import app, get_graph, get_od_pairs
from backend.tests.test_facility_placement import build_graph, pair


def test_placement_api_returns_map_and_recomputed_od_results() -> None:
    graph = build_graph()
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_od_pairs] = lambda: [
        pair("A", 0, 2), pair("B", 0, 1)
    ]
    try:
        response = TestClient(app).get("/api/placement", params={"budget_m": 100})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["rerouted_reduction_m"] == 200.0
    assert result["summary"]["route_changed_od_count"] == 0
    assert len(result["od_comparison"]) == 2
    assert result["candidates"]["type"] == "FeatureCollection"
    assert sum(
        feature["properties"]["selected"]
        for feature in result["candidates"]["features"]
    ) == 1
    assert graph[0][1][0]["cycleway"] == "no"


def test_placement_api_rejects_negative_budget() -> None:
    response = TestClient(app).get("/api/placement", params={"budget_m": -1})
    assert response.status_code == 422
