"""Run the reproducible Phase 5 route comparison and sensitivity experiment."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from backend.app.evaluation import (
    evaluate_profiles,
    evaluate_sensitivity,
    default_od_pairs_path,
    load_od_pairs,
    summarize_sensitivity,
)
from backend.app.routing import load_graph


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_evaluation(
    *,
    graph_path: Path,
    od_path: Path,
    comparison_path: Path,
    sensitivity_path: Path,
    summary_path: Path,
) -> dict[str, int]:
    graph = load_graph(graph_path)
    od_pairs = load_od_pairs(od_path)
    comparison = evaluate_profiles(graph, od_pairs)
    sensitivity = evaluate_sensitivity(graph, od_pairs)
    summary = summarize_sensitivity(sensitivity)

    for frame, path in (
        (comparison, comparison_path),
        (sensitivity, sensitivity_path),
        (summary, summary_path),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False, encoding="utf-8-sig")

    return {
        "comparison_rows": len(comparison),
        "sensitivity_rows": len(sensitivity),
        "summary_rows": len(summary),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5の経路評価結果をCSVに保存します")
    parser.add_argument(
        "--graph",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "sample_bike.graphml",
    )
    parser.add_argument(
        "--od-pairs",
        type=Path,
        default=default_od_pairs_path(PROJECT_ROOT),
    )
    parser.add_argument(
        "--comparison-output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "route_comparison.csv",
    )
    parser.add_argument(
        "--sensitivity-output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "sensitivity_analysis.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "sensitivity_summary.csv",
    )
    args = parser.parse_args(argv)
    try:
        counts = run_evaluation(
            graph_path=args.graph,
            od_path=args.od_pairs,
            comparison_path=args.comparison_output,
            sensitivity_path=args.sensitivity_output,
            summary_path=args.summary_output,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"評価を開始できません: {exc}", file=sys.stderr)
        return 1
    print(f"評価完了: {counts}")
    print(f"比較結果: {args.comparison_output}")
    print(f"感度分析: {args.sensitivity_output}")
    print(f"感度集計: {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
