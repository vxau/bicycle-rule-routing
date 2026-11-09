"""Serve an explicitly synthetic graph for the optional browser smoke test."""

import uvicorn

from backend.app.main import app, get_graph, get_od_pairs
from backend.tests.test_facility_inventory import inventory_graph
from backend.tests.test_facility_placement import pair


if __name__ == "__main__":
    graph = inventory_graph()
    app.dependency_overrides[get_graph] = lambda: graph
    app.dependency_overrides[get_od_pairs] = lambda: [pair("fixture-1", 0, 5)]
    uvicorn.run(app, host="127.0.0.1", port=8001)
