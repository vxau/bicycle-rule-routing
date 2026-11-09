"""Inventory OSM facility information for a human survey, without inferring absence."""

from __future__ import annotations

import hashlib
import json

import networkx as nx
from shapely.geometry import LineString, mapping

from backend.app.facility_placement import facility_state, segment_key
from backend.app.routing import CYCLEWAY_TAGS, _tag_values


def build_facility_inventory(graph: nx.MultiDiGraph) -> dict[str, object]:
    groups = {}
    for u, v, key, data in graph.edges(keys=True, data=True):
        groups.setdefault(segment_key(u, v, key), []).append((u, v, key, data))

    states = {
        state: {"segment_count": 0, "length_m": 0.0}
        for state in ("present", "explicit_absent", "unknown")
    }
    features = []
    for identity, members in sorted(groups.items()):
        members.sort(key=lambda item: tuple(str(value) for value in item[:3]))
        directions = []
        names = set()
        for u, v, key, data in members:
            names.update(_tag_values(data.get("name")))
            directions.append({
                "u": str(u), "v": str(v), "key": str(key),
                "facility_state": facility_state(data),
                "osm_ids": _tag_values(data.get("osmid")),
                "tags": {tag: _tag_values(data.get(tag)) for tag in CYCLEWAY_TAGS},
            })
        direction_states = {direction["facility_state"] for direction in directions}
        conflict = len(direction_states) > 1
        state = "unknown" if conflict else next(iter(direction_states))
        u, v, _, data = members[0]
        length = max(float(member[3]["length"]) for member in members)
        geometry = data.get("geometry")
        if geometry is None:
            geometry = LineString([
                (graph.nodes[u]["x"], graph.nodes[u]["y"]),
                (graph.nodes[v]["x"], graph.nodes[v]["y"]),
            ])
        features.append({
            "type": "Feature",
            "geometry": mapping(geometry),
            "properties": {
                "segment_id": "|".join(identity),
                "name": " / ".join(sorted(name for name in names if name)),
                "facility_state": state,
                "direction_conflict": conflict,
                "length_m": length,
                "start_lat": float(graph.nodes[u]["y"]),
                "start_lon": float(graph.nodes[u]["x"]),
                "end_lat": float(graph.nodes[v]["y"]),
                "end_lon": float(graph.nodes[v]["x"]),
                "directions": directions,
            },
        })
        states[state]["segment_count"] += 1
        states[state]["length_m"] += length

    total_length = sum(row["length_m"] for row in states.values())
    for row in states.values():
        row["length_m"] = round(row["length_m"], 2)
    fingerprint = json.dumps(features, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return {
        "type": "FeatureCollection", "features": features,
        "dataset_id": hashlib.sha256(fingerprint.encode("utf-8")).hexdigest(),
        "summary": {
            "segment_count": len(features),
            "total_length_m": round(total_length, 2),
            "states": states,
        },
    }
