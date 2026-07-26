from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_root_serves_research_map_shell() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="map"' in response.text
    assert 'id="api-status"' in response.text
    assert 'id="data-status"' in response.text

