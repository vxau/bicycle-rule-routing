from functools import lru_cache
from pathlib import Path
from typing import Annotated

import networkx as nx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.evaluation import ODPair, default_od_pairs_path, load_od_pairs
from backend.app.facility_placement import candidate_geojson, evaluate_placement
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


@lru_cache(maxsize=1)
def get_od_pairs() -> list[ODPair]:
    try:
        return load_od_pairs(default_od_pairs_path(PROJECT_ROOT))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="評価用ODペアがありません。OD生成スクリプトを実行してください",
        ) from exc


@app.get("/api/placement")
def placement(
    graph: Annotated[nx.MultiDiGraph, Depends(get_graph)],
    od_pairs: Annotated[list[ODPair], Depends(get_od_pairs)],
    budget_m: Annotated[float, Query(ge=0, le=20_000)] = 1_000.0,
) -> dict[str, object]:
    candidates, selected, summary, comparisons = evaluate_placement(
        graph, od_pairs, budget_m=budget_m
    )
    return {
        "summary": summary,
        "candidates": candidate_geojson(graph, candidates, selected),
        "od_comparison": comparisons,
    }


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
