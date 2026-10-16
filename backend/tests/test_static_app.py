from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def test_root_serves_research_map_shell() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="map"' in response.text
    assert 'id="api-status"' in response.text
    assert 'id="data-status"' in response.text
    assert 'id="route-status"' in response.text
    assert 'id="route-summary"' in response.text
    assert 'id="reset-route"' in response.text
    assert 'id="profile-legend"' in response.text
    assert 'id="route-comparison"' in response.text
    assert 'id="route-comparison-body"' in response.text
    assert 'id="metric-profile"' in response.text


def test_placement_shell_has_map_toggle_and_before_after_results() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="show-placement"' in response.text
    assert 'id="placement-status"' in response.text
    assert 'id="placement-summary"' in response.text
    assert 'id="placement-od-body"' in response.text
