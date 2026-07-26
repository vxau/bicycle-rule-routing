from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
from dotenv import dotenv_values

from backend.app.osm_analysis import (
    build_network_summary,
    calculate_tag_coverage,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
CACHE_DIR = PROJECT_ROOT / ".cache" / "osmnx"

DEFAULT_CONFIG = {
    "OSM_CENTER_LAT": "35.681236",
    "OSM_CENTER_LON": "139.767125",
    "OSM_DISTANCE_METERS": "500",
    "OSM_PLACE_LABEL": "Tokyo Station",
}

WAY_TAGS = [
    "access",
    "bicycle",
    "bridge",
    "cycleway",
    "cycleway:left",
    "cycleway:right",
    "cycleway:both",
    "highway",
    "junction",
    "lanes",
    "maxspeed",
    "name",
    "oneway",
    "oneway:bicycle",
    "service",
    "surface",
    "tunnel",
    "width",
]

NODE_TAGS = [
    "highway",
    "junction",
    "crossing",
    "bicycle",
    "traffic_signals",
]

COVERAGE_TAGS = [
    "oneway",
    "oneway:bicycle",
    "bicycle",
    "cycleway",
    "cycleway:left",
    "cycleway:right",
    "cycleway:both",
    "highway",
    "maxspeed",
    "lanes",
    "width",
    "surface",
    "access",
]


@dataclass(frozen=True)
class FetchConfig:
    latitude: float
    longitude: float
    distance_m: int
    place_label: str


def parse_fetch_config(values: Mapping[str, str]) -> FetchConfig:
    try:
        latitude = float(values["OSM_CENTER_LAT"])
        longitude = float(values["OSM_CENTER_LON"])
        distance_m = int(values["OSM_DISTANCE_METERS"])
        place_label = values["OSM_PLACE_LABEL"].strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("OSM取得設定の値を確認してください") from exc

    if not -90 <= latitude <= 90:
        raise ValueError("OSM_CENTER_LAT must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("OSM_CENTER_LON must be between -180 and 180")
    if not 100 <= distance_m <= 5000:
        raise ValueError("OSM_DISTANCE_METERS must be between 100 and 5000")
    if not place_label:
        raise ValueError("OSM_PLACE_LABEL must not be empty")

    return FetchConfig(
        latitude=latitude,
        longitude=longitude,
        distance_m=distance_m,
        place_label=place_label,
    )


def load_fetch_config() -> FetchConfig:
    file_values = {
        key: value
        for key, value in dotenv_values(PROJECT_ROOT / ".env").items()
        if value is not None
    }
    environment_values = {
        key: os.environ[key]
        for key in DEFAULT_CONFIG
        if key in os.environ
    }
    return parse_fetch_config(
        {
            **DEFAULT_CONFIG,
            **file_values,
            **environment_values,
        }
    )


def prepare_geojson_frame(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Convert list-like OSM attributes to values GeoJSON drivers can write."""
    prepared = frame.reset_index()
    for column in prepared.columns:
        if column == prepared.geometry.name:
            continue
        prepared[column] = prepared[column].map(_serialize_attribute)
    return prepared


def main() -> int:
    try:
        config = load_fetch_config()
        _prepare_directories()
        _configure_osmnx()
        print(
            f"OSM取得開始: {config.place_label}, "
            f"({config.latitude}, {config.longitude}), "
            f"半径{config.distance_m}m"
        )
        graph = ox.graph.graph_from_point(
            (config.latitude, config.longitude),
            dist=config.distance_m,
            network_type="bike",
        )
        if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
            raise RuntimeError("取得した道路ネットワークが空です")

        nodes, edges = ox.convert.graph_to_gdfs(graph)
        coverage = calculate_tag_coverage(edges, COVERAGE_TAGS)
        basic_stats = ox.stats.basic_stats(graph)
        summary = build_network_summary(
            graph.number_of_nodes(),
            graph.number_of_edges(),
            edges,
            street_length_m=float(basic_stats["street_length_total"]),
        )
        summary.update(_research_metadata(config, nodes))

        graphml_path = RAW_DIR / "sample_bike.graphml"
        nodes_path = EXPORT_DIR / "sample_nodes.geojson"
        edges_path = EXPORT_DIR / "sample_edges.geojson"
        coverage_path = PROCESSED_DIR / "tag_coverage.csv"
        summary_path = PROCESSED_DIR / "summary.json"

        ox.io.save_graphml(graph, filepath=graphml_path)
        prepare_geojson_frame(nodes).to_file(
            nodes_path,
            driver="GeoJSON",
            index=False,
        )
        prepare_geojson_frame(edges).to_file(
            edges_path,
            driver="GeoJSON",
            index=False,
        )
        coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"取得完了: nodes={summary['node_count']}, edges={summary['edge_count']}")
        print(f"有向エッジ総延長: {summary['total_edge_length_km']} km")
        print(f"街路総延長: {summary['street_length_km']} km")
        print(f"GraphML: {graphml_path}")
        print(f"GeoJSON: {edges_path}")
        print(f"属性集計: {coverage_path}")
        return 0
    except Exception as exc:
        print(f"OSM取得に失敗しました: {exc}", file=sys.stderr)
        return 1


def _prepare_directories() -> None:
    for directory in (RAW_DIR, PROCESSED_DIR, EXPORT_DIR, CACHE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def _configure_osmnx() -> None:
    ox.settings.cache_folder = CACHE_DIR
    ox.settings.use_cache = True
    ox.settings.log_console = True
    ox.settings.useful_tags_way = list(
        dict.fromkeys([*ox.settings.useful_tags_way, *WAY_TAGS])
    )
    ox.settings.useful_tags_node = list(
        dict.fromkeys([*ox.settings.useful_tags_node, *NODE_TAGS])
    )


def _serialize_attribute(value: object) -> object:
    if isinstance(value, (list, tuple, set, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _research_metadata(
    config: FetchConfig,
    nodes: gpd.GeoDataFrame,
) -> dict[str, str | float | int]:
    highway_values = nodes.get(
        "highway",
        pd.Series(index=nodes.index, dtype=object),
    )
    crossing_values = nodes.get(
        "crossing",
        pd.Series(index=nodes.index, dtype=object),
    )
    return {
        "place_label": config.place_label,
        "center_latitude": config.latitude,
        "center_longitude": config.longitude,
        "distance_m": config.distance_m,
        "traffic_signal_node_count": int(
            highway_values.map(
                lambda value: _contains_tag_value(value, "traffic_signals")
            ).sum()
        ),
        "stop_node_count": int(
            highway_values.map(
                lambda value: _contains_tag_value(value, "stop")
            ).sum()
        ),
        "crossing_node_count": int(crossing_values.notna().sum()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "osmnx_version": ox.__version__,
    }


def _contains_tag_value(value: object, expected: str) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(str(item) == expected for item in value)
    return str(value) == expected


if __name__ == "__main__":
    raise SystemExit(main())
