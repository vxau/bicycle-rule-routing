from __future__ import annotations

import hashlib
import json
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import pandas as pd

from backend.app.routing import (
    ROUTE_PROFILES,
    ROUTE_PROFILE_IDS,
    ProfileMap,
    build_route_result,
    find_nearest_node,
)


OD_PAIR_COLUMNS = (
    "od_id",
    "origin_label",
    "origin_lat",
    "origin_lon",
    "destination_label",
    "destination_lat",
    "destination_lon",
    "distance_band",
)
COORDINATE_COLUMNS = (
    "origin_lat",
    "origin_lon",
    "destination_lat",
    "destination_lon",
)
DISTANCE_BANDS = {"short", "medium", "long"}

ROUTE_COMPARISON_COLUMNS = (
    "od_id",
    "origin_label",
    "origin_lat",
    "origin_lon",
    "destination_label",
    "destination_lat",
    "destination_lon",
    "distance_band",
    "snapped_origin_node",
    "snapped_destination_node",
    "profile_id",
    "profile_label",
    "available",
    "error",
    "distance_m",
    "distance_increase_pct",
    "major_road_pct",
    "cycleway_pct",
    "traffic_signal_count",
    "unknown_attribute_pct",
    "profile_cost",
    "route_signature",
    "same_as_shortest",
    "same_route_profile_count",
    "same_route_profile_pct",
    "unique_route_count",
)


@dataclass(frozen=True)
class ODPair:
    od_id: str
    origin_label: str
    origin_lat: float
    origin_lon: float
    destination_label: str
    destination_lat: float
    destination_lon: float
    distance_band: str


def route_signature(
    edge_path: Sequence[tuple[Hashable, Hashable, Hashable]],
) -> str:
    normalized = [[str(value) for value in edge] for edge in edge_path]
    payload = json.dumps(
        normalized, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_od_pairs(path: Path) -> list[ODPair]:
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError as exc:
        raise ValueError("ODペアCSVが空です") from exc

    if frame.empty:
        raise ValueError("ODペアCSVが空です")

    actual_columns = set(frame.columns)
    required_columns = set(OD_PAIR_COLUMNS)
    missing = required_columns - actual_columns
    extra = actual_columns - required_columns
    if missing:
        raise ValueError(f"必須列が不足しています: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"未定義の列があります: {', '.join(sorted(extra))}")

    frame = frame.loc[:, OD_PAIR_COLUMNS].copy()
    identifiers = frame["od_id"].fillna("").astype(str).str.strip()
    if identifiers.eq("").any():
        raise ValueError("od_idに空欄があります")
    if identifiers.duplicated().any():
        raise ValueError("od_idが重複しています")
    frame["od_id"] = identifiers

    try:
        for column in COORDINATE_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("緯度・経度は数値で指定してください") from exc

    latitude_columns = ("origin_lat", "destination_lat")
    longitude_columns = ("origin_lon", "destination_lon")
    if any(not frame[column].between(-90, 90).all() for column in latitude_columns):
        raise ValueError("緯度は-90から90の範囲で指定してください")
    if any(
        not frame[column].between(-180, 180).all()
        for column in longitude_columns
    ):
        raise ValueError("経度は-180から180の範囲で指定してください")

    frame["distance_band"] = (
        frame["distance_band"].fillna("").astype(str).str.strip()
    )
    invalid_bands = set(frame["distance_band"]) - DISTANCE_BANDS
    if invalid_bands:
        raise ValueError(
            "distance_bandはshort、medium、longのいずれかで指定してください"
        )

    pairs: list[ODPair] = []
    for row in frame.to_dict(orient="records"):
        pairs.append(
            ODPair(
                od_id=str(row["od_id"]),
                origin_label=str(row["origin_label"]),
                origin_lat=float(row["origin_lat"]),
                origin_lon=float(row["origin_lon"]),
                destination_label=str(row["destination_label"]),
                destination_lat=float(row["destination_lat"]),
                destination_lon=float(row["destination_lon"]),
                distance_band=str(row["distance_band"]),
            )
        )
    return pairs


def evaluate_profiles(
    graph: nx.MultiDiGraph,
    od_pairs: Sequence[ODPair],
    *,
    profiles: ProfileMap = ROUTE_PROFILES,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for pair in od_pairs:
        source = find_nearest_node(
            graph,
            latitude=pair.origin_lat,
            longitude=pair.origin_lon,
        )
        target = find_nearest_node(
            graph,
            latitude=pair.destination_lat,
            longitude=pair.destination_lon,
        )
        pair_rows: list[dict[str, object]] = []

        for profile_id in ROUTE_PROFILE_IDS:
            row = _base_evaluation_row(
                pair=pair,
                source=source,
                target=target,
                profile_id=profile_id,
                profile_label=str(profiles[profile_id]["label"]),
            )
            try:
                result = build_route_result(
                    graph,
                    source=source,
                    target=target,
                    profile_id=profile_id,
                    profiles=profiles,
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
                row.update(
                    {
                        "available": False,
                        "error": str(exc) or "経路が見つかりません",
                    }
                )
            else:
                summary = result["summary"]
                row.update(
                    {
                        "available": True,
                        "error": pd.NA,
                        "distance_m": summary["distance_m"],
                        "major_road_pct": summary["major_road_pct"],
                        "cycleway_pct": summary["cycleway_pct"],
                        "traffic_signal_count": summary[
                            "traffic_signal_count"
                        ],
                        "unknown_attribute_pct": summary[
                            "unknown_attribute_pct"
                        ],
                        "profile_cost": summary["profile_cost"],
                        "route_signature": route_signature(
                            result["edge_path"]
                        ),
                    }
                )
            pair_rows.append(row)

        _add_pair_comparison_metrics(pair_rows)
        rows.extend(pair_rows)

    return pd.DataFrame(rows, columns=ROUTE_COMPARISON_COLUMNS)


def _base_evaluation_row(
    *,
    pair: ODPair,
    source: Hashable,
    target: Hashable,
    profile_id: str,
    profile_label: str,
) -> dict[str, object]:
    row: dict[str, object] = {
        "od_id": pair.od_id,
        "origin_label": pair.origin_label,
        "origin_lat": pair.origin_lat,
        "origin_lon": pair.origin_lon,
        "destination_label": pair.destination_label,
        "destination_lat": pair.destination_lat,
        "destination_lon": pair.destination_lon,
        "distance_band": pair.distance_band,
        "snapped_origin_node": source,
        "snapped_destination_node": target,
        "profile_id": profile_id,
        "profile_label": profile_label,
        "available": False,
        "error": pd.NA,
    }
    for column in ROUTE_COMPARISON_COLUMNS:
        row.setdefault(column, pd.NA)
    return row


def _add_pair_comparison_metrics(
    pair_rows: list[dict[str, object]],
) -> None:
    available_rows = [row for row in pair_rows if row["available"]]
    shortest = next(
        (
            row
            for row in available_rows
            if row["profile_id"] == "shortest"
        ),
        None,
    )
    signatures = [str(row["route_signature"]) for row in available_rows]
    signature_counts = {
        signature: signatures.count(signature) for signature in set(signatures)
    }
    unique_route_count = len(signature_counts)
    available_count = len(available_rows)

    for row in pair_rows:
        if not row["available"]:
            continue
        row["unique_route_count"] = unique_route_count
        signature = str(row["route_signature"])
        same_count = signature_counts[signature]
        row["same_route_profile_count"] = same_count
        row["same_route_profile_pct"] = round(
            same_count / available_count * 100, 2
        )

        if shortest is None:
            continue
        shortest_distance = float(shortest["distance_m"])
        if shortest_distance > 0:
            row["distance_increase_pct"] = round(
                (float(row["distance_m"]) - shortest_distance)
                / shortest_distance
                * 100,
                2,
            )
        else:
            row["distance_increase_pct"] = 0.0
        row["same_as_shortest"] = (
            row["route_signature"] == shortest["route_signature"]
        )
