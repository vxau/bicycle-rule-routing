"""Select a reproducible set of origin-destination pairs from a road graph."""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections.abc import Hashable, Sequence
from dataclasses import asdict
from itertools import cycle
from pathlib import Path

import networkx as nx
import pandas as pd

from backend.app.evaluation import OD_PAIR_COLUMNS, ODPair
from backend.app.routing import load_graph


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISTANCE_BANDS = {
    "short": (300.0, 1_000.0, 5),
    "medium": (1_000.0, 2_500.0, 10),
    "long": (2_500.0, 6_000.0, 5),
}


def _distance_and_bearing(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> tuple[float, int]:
    lat1, lon1, lat2, lon2 = map(
        math.radians,
        (origin_lat, origin_lon, destination_lat, destination_lon),
    )
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    distance = 6_371_008.8 * 2 * math.asin(min(1.0, math.sqrt(value)))
    east = math.sin(delta_lon) * math.cos(lat2)
    north = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    )
    bearing = (math.degrees(math.atan2(east, north)) + 360) % 360
    return distance, int(bearing // 45)


def select_od_pairs(
    graph: nx.MultiDiGraph,
    *,
    seed: int = 20260914,
) -> list[ODPair]:
    components = nx.strongly_connected_components(graph)
    largest = max(components, key=len, default=set())
    if len(largest) < 2:
        raise ValueError("20組のODペアを選定できません")

    rng = random.Random(seed)
    nodes = sorted(largest, key=str)
    sampled = rng.sample(nodes, k=min(400, len(nodes)))
    candidates: dict[str, dict[int, list[tuple[Hashable, Hashable]]]] = {
        band: {bearing: [] for bearing in range(8)} for band in DISTANCE_BANDS
    }

    for origin in sampled:
        origin_data = graph.nodes[origin]
        for destination in sampled:
            if origin == destination:
                continue
            destination_data = graph.nodes[destination]
            distance, bearing = _distance_and_bearing(
                float(origin_data["y"]),
                float(origin_data["x"]),
                float(destination_data["y"]),
                float(destination_data["x"]),
            )
            for band, (minimum, maximum, _count) in DISTANCE_BANDS.items():
                if minimum <= distance < maximum:
                    candidates[band][bearing].append((origin, destination))
                    break

    selected: list[ODPair] = []
    for band, (_minimum, _maximum, count) in DISTANCE_BANDS.items():
        buckets = candidates[band]
        for options in buckets.values():
            rng.shuffle(options)
        chosen: list[tuple[Hashable, Hashable]] = []
        for bearing in cycle(range(8)):
            if not any(buckets.values()):
                break
            if buckets[bearing]:
                chosen.append(buckets[bearing].pop())
            if len(chosen) == count:
                break
        if len(chosen) != count:
            raise ValueError("20組のODペアを選定できません")

        for origin, destination in chosen:
            number = len(selected) + 1
            origin_data = graph.nodes[origin]
            destination_data = graph.nodes[destination]
            selected.append(
                ODPair(
                    od_id=f"OD-{number:02d}",
                    origin_label=f"地点{number:02d}-A",
                    origin_lat=float(origin_data["y"]),
                    origin_lon=float(origin_data["x"]),
                    destination_label=f"地点{number:02d}-B",
                    destination_lat=float(destination_data["y"]),
                    destination_lon=float(destination_data["x"]),
                    distance_band=band,
                )
            )
    return selected


def write_od_pairs(od_pairs: Sequence[ODPair], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(pair) for pair in od_pairs], columns=OD_PAIR_COLUMNS).to_csv(
        path, index=False, encoding="utf-8-sig"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="評価用ODペアを選定します")
    parser.add_argument(
        "--graph",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "sample_bike.graphml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "input" / "od_pairs.csv",
    )
    parser.add_argument("--seed", type=int, default=20260914)
    args = parser.parse_args(argv)
    try:
        graph = load_graph(args.graph)
        pairs = select_od_pairs(graph, seed=args.seed)
        write_od_pairs(pairs, args.output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ODペアを選定できません: {exc}", file=sys.stderr)
        return 1
    counts = {band: sum(pair.distance_band == band for pair in pairs) for band in DISTANCE_BANDS}
    print(f"ODペア: {len(pairs)}組 {counts}")
    print(f"保存先: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
