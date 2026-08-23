import networkx as nx
from fastapi.testclient import TestClient
from shapely.geometry import LineString

from backend.app.main import app, get_graph


def build_api_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph(crs="EPSG:4326")
    graph.add_node(1, x=139.0000, y=35.0000)
    graph.add_node(2, x=139.0010, y=35.0000)
    graph.add_edge(
        1,
        2,
        key=0,
        length=120.0,
        highway="residential",
        cycleway="lane",
        maxspeed="30",
        width="4",
        surface="asphalt",
        geometry=LineString([(139.0000, 35.0000), (139.0010, 35.0000)]),
    )
    return graph


def test_shortest_route_api_snaps_coordinates_and_returns_geojson() -> None:
    app.dependency_overrides[get_graph] = build_api_graph
    client = TestClient(app)

    try:
        response = client.get(
            "/api/routes/shortest",
            params={
                "start_lat": 35.0000,
                "start_lon": 139.0000,
                "end_lat": 35.0000,
                "end_lon": 139.0010,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["route"]["type"] == "FeatureCollection"
    assert body["summary"]["distance_m"] == 120.0
    assert body["snapped_nodes"] == {"start": 1, "end": 2}


def test_shortest_route_api_reports_unreachable_destination() -> None:
    graph = build_api_graph()
    graph.add_node(3, x=140.0000, y=36.0000)
    app.dependency_overrides[get_graph] = lambda: graph
    client = TestClient(app)

    try:
        response = client.get(
            "/api/routes/shortest",
            params={
                "start_lat": 35.0000,
                "start_lon": 139.0000,
                "end_lat": 36.0000,
                "end_lon": 140.0000,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "経路が見つかりません"
