"""Export a fixed-route screening of existing-road cycling improvements."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from backend.app.evaluation import load_od_pairs
from backend.app.facility_placement import score_candidates, select_candidates
from backend.app.routing import load_graph


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_placement(
    *,
    graph_path: Path,
    od_path: Path,
    output_path: Path,
    summary_path: Path,
    budget_m: float = 1_000.0,
) -> dict[str, float | int | str]:
    graph = load_graph(graph_path)
    pairs = load_od_pairs(od_path)
    candidates, statistics = score_candidates(graph, pairs)
    selected = select_candidates(candidates, budget_m=budget_m)
    selected_ids = {candidate.segment_id for candidate in selected}
    rows = [
        {**asdict(candidate), "selected": candidate.segment_id in selected_ids}
        for candidate in candidates
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        rows,
        columns=[
            "segment_id", "start_lat", "start_lon", "end_lat", "end_lon",
            "length_m", "od_count", "benefit_m", "selected",
        ],
    ).to_csv(output_path, index=False, encoding="utf-8-sig")

    benefit = round(sum(candidate.benefit_m for candidate in selected), 2)
    summary: dict[str, float | int | str] = {
        "model": "fixed_route_explicit_absence",
        "profile_id": "balanced",
        "budget_m": budget_m,
        "used_length_m": round(sum(candidate.length_m for candidate in selected), 2),
        "selected_count": len(selected),
        "selected_benefit_m": benefit,
        "residual_exposure_m": round(
            float(statistics["baseline_exposure_m"]) - benefit, 2
        ),
        **statistics,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="既存道路の自転車設備候補を選定します")
    parser.add_argument(
        "--graph", type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "sample_bike.graphml",
    )
    parser.add_argument(
        "--od-pairs", type=Path,
        default=PROJECT_ROOT / "data" / "input" / "od_pairs.csv",
    )
    parser.add_argument("--budget-m", type=float, default=1_000.0)
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "facility_candidates.csv",
    )
    parser.add_argument(
        "--summary-output", type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "facility_placement_summary.json",
    )
    args = parser.parse_args(argv)
    try:
        summary = run_placement(
            graph_path=args.graph,
            od_path=args.od_pairs,
            output_path=args.output,
            summary_path=args.summary_output,
            budget_m=args.budget_m,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"候補を選定できません: {exc}", file=sys.stderr)
        return 1
    print(f"候補選定完了: {summary}")
    print(f"候補CSV: {args.output}")
    print(f"集計JSON: {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
