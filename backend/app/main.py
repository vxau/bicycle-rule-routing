from functools import lru_cache
from pathlib import Path
from typing import Annotated

import networkx as nx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.routing import (
    build_route_comparison,
    build_route_result,
    find_nearest_node,
    load_graph,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
GRAPHML_PATH = PROJECT_ROOT / "data" / "raw" / "sample_bike.graphml"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Bicycle Rule Routing Research API")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
app.mount("/data", StaticFiles(directory=EXPORT_DIR), name="data")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "bicycle-rule-routing-api",
    }


@lru_cache(maxsize=1)
def get_graph() -> nx.MultiDiGraph:
    try:
        return load_graph(GRAPHML_PATH)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="道路グラフがありません。OSM取得スクリプトを実行してください",
        ) from exc


@app.get("/api/routes/shortest")
def shortest_route(
    start_lat: Annotated[float, Query(ge=-90, le=90)],
    start_lon: Annotated[float, Query(ge=-180, le=180)],
    end_lat: Annotated[float, Query(ge=-90, le=90)],
    end_lon: Annotated[float, Query(ge=-180, le=180)],
    graph: Annotated[nx.MultiDiGraph, Depends(get_graph)],
) -> dict[str, object]:
    start_node = find_nearest_node(
        graph,
        latitude=start_lat,
        longitude=start_lon,
    )
    end_node = find_nearest_node(
        graph,
        latitude=end_lat,
        longitude=end_lon,
    )
    try:
        result = build_route_result(graph, source=start_node, target=end_node)
    except nx.NetworkXNoPath as exc:
        raise HTTPException(status_code=404, detail="経路が見つかりません") from exc

    return {
        "route": result["geojson"],
        "summary": result["summary"],
        "snapped_nodes": {"start": start_node, "end": end_node},
    }


@app.get("/api/routes/compare")
def compare_routes(
    start_lat: Annotated[float, Query(ge=-90, le=90)],
    start_lon: Annotated[float, Query(ge=-180, le=180)],
    end_lat: Annotated[float, Query(ge=-90, le=90)],
    end_lon: Annotated[float, Query(ge=-180, le=180)],
    graph: Annotated[nx.MultiDiGraph, Depends(get_graph)],
) -> dict[str, object]:
    start_node = find_nearest_node(
        graph,
        latitude=start_lat,
        longitude=start_lon,
    )
    end_node = find_nearest_node(
        graph,
        latitude=end_lat,
        longitude=end_lon,
    )
    try:
        routes = build_route_comparison(
            graph,
            source=start_node,
            target=end_node,
        )
    except nx.NetworkXNoPath as exc:
        raise HTTPException(status_code=404, detail="経路が見つかりません") from exc

    return {
        "routes": routes,
        "snapped_nodes": {"start": start_node, "end": end_node},
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")
