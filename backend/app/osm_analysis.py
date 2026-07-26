from collections.abc import Iterable
from typing import Any

import geopandas as gpd
import pandas as pd


EXPLICIT_ABSENT_VALUES = {"no", "none"}


def classify_tag(value: object) -> str:
    """Classify an OSM tag without treating missing data as absence."""
    if isinstance(value, (list, tuple, set)):
        states = [classify_tag(item) for item in value]
        if "present" in states:
            return "present"
        if "explicit_absent" in states:
            return "explicit_absent"
        return "unknown"

    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "present" if value else "explicit_absent"
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return "unknown"
        if normalized in EXPLICIT_ABSENT_VALUES:
            return "explicit_absent"
        return "present"

    try:
        if bool(pd.isna(value)):
            return "unknown"
    except (TypeError, ValueError):
        pass
    return "present"


def calculate_tag_coverage(
    edges: gpd.GeoDataFrame,
    tags: Iterable[str],
) -> pd.DataFrame:
    """Calculate length-weighted recorded and unknown proportions per tag."""
    if "length" not in edges.columns:
        raise ValueError("edges must contain a length column")

    lengths = pd.to_numeric(edges["length"], errors="coerce").fillna(0.0)
    total_length = float(lengths.sum())
    rows: list[dict[str, Any]] = []

    for tag in tags:
        values = edges[tag] if tag in edges.columns else pd.Series(
            [None] * len(edges),
            index=edges.index,
            dtype=object,
        )
        states = values.map(classify_tag)
        present_length = float(lengths[states == "present"].sum())
        absent_length = float(lengths[states == "explicit_absent"].sum())
        unknown_length = float(lengths[states == "unknown"].sum())
        recorded_length = present_length + absent_length

        rows.append(
            {
                "tag": tag,
                "total_length_m": total_length,
                "recorded_length_m": recorded_length,
                "present_length_m": present_length,
                "explicit_absent_length_m": absent_length,
                "unknown_length_m": unknown_length,
                "recorded_pct": _percentage(recorded_length, total_length),
                "unknown_pct": _percentage(unknown_length, total_length),
            }
        )

    return pd.DataFrame(rows)


def build_network_summary(
    node_count: int,
    edge_count: int,
    edges: gpd.GeoDataFrame,
) -> dict[str, float | int]:
    """Build the basic statistics used in the first research report."""
    if "length" not in edges.columns:
        raise ValueError("edges must contain a length column")

    total_length = float(
        pd.to_numeric(edges["length"], errors="coerce").fillna(0.0).sum()
    )
    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "total_edge_length_m": total_length,
        "total_edge_length_km": round(total_length / 1000, 3),
    }


def _percentage(part: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round(part / total * 100, 2)
